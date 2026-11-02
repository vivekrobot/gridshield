"""A small, dependency-light 1D-CNN implemented with NumPy.

Why not Keras?  The paper's deployment target is an ESP32 running TensorFlow
Lite Micro, but the training machine here only has Python 3.14/3.15, for which
no TensorFlow wheels exist.  This module implements exactly the architecture
that is exported to the firmware (conv1d -> relu -> maxpool -> conv1d -> relu ->
maxpool -> global avg/max -> dense -> softmax) with hand-written backprop.

The same weights are therefore used in three places:

* NumPy training / evaluation (this file),
* the cloud simulator and tests (``ml.infer``),
* the ESP32 firmware (``model_weights.h`` generated from the .npz).

``ml/export_tflite.py`` contains the optional conversion path for machines that
do have TensorFlow (Python <= 3.12); it rebuilds a Keras model with these exact
weights and produces a quantised .tflite flatbuffer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .config import (
    CONV1_FILTERS,
    CONV1_KERNEL,
    CONV2_FILTERS,
    CONV2_KERNEL,
    DENSE_UNITS,
    N_CHANNELS,
    N_CLASSES,
    POOL_SIZE,
    WINDOW,
)


# ---------------------------------------------------------------------------
# Primitive layers
# ---------------------------------------------------------------------------
def im2col(x: np.ndarray, kernel: int) -> np.ndarray:
    """(N, L, C) -> (N, L-K+1, K*C), flattening k-major then channel."""
    n, length, channels = x.shape
    out_len = length - kernel + 1
    windows = np.lib.stride_tricks.sliding_window_view(x, kernel, axis=1)  # N,Lout,C,K
    return windows.transpose(0, 1, 3, 2).reshape(n, out_len, kernel * channels)


def col2im(cols: np.ndarray, kernel: int, channels: int, length: int) -> np.ndarray:
    n, out_len, _ = cols.shape
    dx = np.zeros((n, length, channels), dtype=cols.dtype)
    for k in range(kernel):
        dx[:, k : k + out_len, :] += cols[:, :, k * channels : (k + 1) * channels]
    return dx


def conv1d_forward(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    kernel, channels, filters = w.shape
    cols = im2col(x, kernel)
    out = cols @ w.reshape(kernel * channels, filters) + b
    return out, cols


def conv1d_backward(
    dout: np.ndarray, cols: np.ndarray, x_shape: tuple[int, int, int], w: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n, length, channels = x_shape
    kernel, _, filters = w.shape
    dout_flat = dout.reshape(-1, filters)
    dw = (cols.reshape(-1, kernel * channels).T @ dout_flat).reshape(w.shape)
    db = dout.sum(axis=(0, 1))
    dcols = (dout_flat @ w.reshape(kernel * channels, filters).T).reshape(cols.shape)
    dx = col2im(dcols, kernel, channels, length)
    return dx, dw, db


def maxpool1d_forward(x: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    n, length, channels = x.shape
    trimmed = length - (length % size)
    xr = x[:, :trimmed, :].reshape(n, trimmed // size, size, channels)
    idx = xr.argmax(axis=2)
    out = np.take_along_axis(xr, idx[:, :, None, :], axis=2).squeeze(2)
    return out, idx


def maxpool1d_backward(dout: np.ndarray, idx: np.ndarray, x_shape: tuple[int, int, int], size: int) -> np.ndarray:
    n, length, channels = x_shape
    trimmed = length - (length % size)
    dxr = np.zeros((n, trimmed // size, size, channels), dtype=dout.dtype)
    np.put_along_axis(dxr, idx[:, :, None, :], dout[:, :, None, :], axis=2)
    dx = np.zeros(x_shape, dtype=dout.dtype)
    dx[:, :trimmed, :] = dxr.reshape(n, trimmed, channels)
    return dx


class Adam:
    """Minimal Adam optimiser with decoupled weight decay."""

    def __init__(self, params: dict[str, np.ndarray], lr: float = 3e-3, weight_decay: float = 1e-4):
        self.params = params
        self.lr = lr
        self.weight_decay = weight_decay
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0

    def step(self, grads: dict[str, np.ndarray], lr: float | None = None) -> None:
        lr = self.lr if lr is None else lr
        self.t += 1
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        for key, grad in grads.items():
            if key not in self.params:
                continue
            self.m[key] = beta1 * self.m[key] + (1 - beta1) * grad
            self.v[key] = beta2 * self.v[key] + (1 - beta2) * (grad * grad)
            m_hat = self.m[key] / (1 - beta1**self.t)
            v_hat = self.v[key] / (1 - beta2**self.t)
            self.params[key] -= lr * (m_hat / (np.sqrt(v_hat) + eps) + self.weight_decay * self.params[key])


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
@dataclass
class CNN1D:
    W1: np.ndarray
    b1: np.ndarray
    W2: np.ndarray
    b2: np.ndarray
    W3: np.ndarray
    b3: np.ndarray
    W4: np.ndarray
    b4: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)

    # -- construction -------------------------------------------------------
    @classmethod
    def initialise(cls, seed: int = 42, n_channels: int = N_CHANNELS, n_classes: int = N_CLASSES) -> "CNN1D":
        rng = np.random.default_rng(seed)

        def he(shape, fan_in):
            return rng.normal(0.0, np.sqrt(2.0 / fan_in), size=shape).astype(np.float32)

        W1 = he((CONV1_KERNEL, n_channels, CONV1_FILTERS), CONV1_KERNEL * n_channels)
        b1 = np.zeros(CONV1_FILTERS, np.float32)
        W2 = he((CONV2_KERNEL, CONV1_FILTERS, CONV2_FILTERS), CONV2_KERNEL * CONV1_FILTERS)
        b2 = np.zeros(CONV2_FILTERS, np.float32)
        l1 = WINDOW - CONV1_KERNEL + 1
        l2 = l1 // POOL_SIZE - CONV2_KERNEL + 1
        l3 = l2 // POOL_SIZE
        flat = CONV2_FILTERS * 2
        W3 = he((flat, DENSE_UNITS), flat)
        b3 = np.zeros(DENSE_UNITS, np.float32)
        W4 = rng.normal(0.0, np.sqrt(2.0 / DENSE_UNITS), size=(DENSE_UNITS, n_classes)).astype(np.float32)
        b4 = np.zeros(n_classes, np.float32)
        model = cls(W1, b1, W2, b2, W3, b3, W4, b4)
        model.meta = {
            "architecture": "1D-CNN",
            "input_shape": [WINDOW, n_channels],
            "conv1": {"filters": CONV1_FILTERS, "kernel": CONV1_KERNEL, "activation": "relu"},
            "pool1": POOL_SIZE,
            "conv2": {"filters": CONV2_FILTERS, "kernel": CONV2_KERNEL, "activation": "relu"},
            "pool2": POOL_SIZE,
            "pool3": "global_avg+global_max",
            "dense": DENSE_UNITS,
            "classes": list(cls.default_classes(n_classes)),
            "l1": l1,
            "l2": l2,
            "l3": l3,
        }
        return model

    @staticmethod
    def default_classes(n_classes: int = N_CLASSES) -> tuple[str, ...]:
        from .config import CLASSES

        return CLASSES[:n_classes]

    # -- inference ----------------------------------------------------------
    def forward(self, x: np.ndarray, cache: bool = False) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        if x.ndim == 2:
            x = x[None, ...]
        if x.ndim != 3 or x.shape[1:] != (WINDOW, self.W1.shape[1]):
            raise ValueError(f"expected (N, {WINDOW}, {self.W1.shape[1]}), got {x.shape}")

        c1, cols1 = conv1d_forward(x, self.W1, self.b1)
        a1 = np.maximum(c1, 0.0)
        p1, idx1 = maxpool1d_forward(a1, POOL_SIZE)

        c2, cols2 = conv1d_forward(p1, self.W2, self.b2)
        a2 = np.maximum(c2, 0.0)
        p2, idx2 = maxpool1d_forward(a2, POOL_SIZE)

        gap = p2.mean(axis=1)
        idx3 = p2.argmax(axis=1)
        gmp = np.take_along_axis(p2, idx3[:, None, :], axis=1).squeeze(1)
        z = np.concatenate([gap, gmp], axis=1)

        h = np.maximum(z @ self.W3 + self.b3, 0.0)
        logits = h @ self.W4 + self.b4

        if cache:
            self._cache = {
                "x": x,
                "cols1": cols1,
                "a1": a1,
                "idx1": idx1,
                "p1": p1,
                "cols2": cols2,
                "a2": a2,
                "idx2": idx2,
                "p2": p2,
                "idx3": idx3,
                "z": z,
                "h": h,
                "logits": logits,
            }
        return logits

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        return softmax(self.forward(x))

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.predict_proba(x).argmax(axis=1)

    # -- training -----------------------------------------------------------
    def backward(self, dlogits: np.ndarray) -> dict[str, np.ndarray]:
        c = self._cache
        dh = dlogits @ self.W4.T
        dW4 = c["h"].T @ dlogits
        db4 = dlogits.sum(axis=0)

        dz_pre = dh * (c["h"] > 0)
        dW3 = c["z"].T @ dz_pre
        db3 = dz_pre.sum(axis=0)
        dz = dz_pre @ self.W3.T

        n, l3, filters = c["p2"].shape
        dgap = dz[:, :filters] / l3
        dgmp = dz[:, filters:]
        dp2 = np.repeat(dgap[:, None, :], l3, axis=1)
        np.put_along_axis(
            dp2,
            c["idx3"][:, None, :],
            np.take_along_axis(dp2, c["idx3"][:, None, :], axis=1) + dgmp[:, None, :],
            axis=1,
        )

        da2 = maxpool1d_backward(dp2, c["idx2"], c["a2"].shape, POOL_SIZE)
        dc2 = da2 * (c["a2"] > 0)
        dp1, dW2, db2 = conv1d_backward(dc2, c["cols2"], c["p1"].shape, self.W2)

        da1 = maxpool1d_backward(dp1, c["idx1"], c["a1"].shape, POOL_SIZE)
        dc1 = da1 * (c["a1"] > 0)
        _, dW1, db1 = conv1d_backward(dc1, c["cols1"], c["x"].shape, self.W1)

        return {"W1": dW1, "b1": db1, "W2": dW2, "b2": db2, "W3": dW3, "b3": db3, "W4": dW4, "b4": db4}

    # -- persistence --------------------------------------------------------
    def state(self) -> dict[str, np.ndarray]:
        return {k: getattr(self, k).copy() for k in ("W1", "b1", "W2", "b2", "W3", "b3", "W4", "b4")}

    def save(self, path: str | Path, extra: dict[str, Any] | None = None) -> None:
        meta = dict(self.meta)
        if extra:
            meta.update(extra)
        np.savez_compressed(
            path,
            **self.state(),
            meta_json=np.array(json.dumps(meta)),
        )

    @classmethod
    def load(cls, path: str | Path) -> "CNN1D":
        data = np.load(path, allow_pickle=False)
        model = cls(
            data["W1"].astype(np.float32),
            data["b1"].astype(np.float32),
            data["W2"].astype(np.float32),
            data["b2"].astype(np.float32),
            data["W3"].astype(np.float32),
            data["b3"].astype(np.float32),
            data["W4"].astype(np.float32),
            data["b4"].astype(np.float32),
        )
        model.meta = json.loads(str(data["meta_json"].item()))
        return model

    @property
    def n_params(self) -> int:
        return int(sum(arr.size for arr in self.state().values()))

    def __repr__(self) -> str:  # pragma: no cover
        return f"CNN1D(params={self.n_params}, input={self.W1.shape[1]}ch x {WINDOW})"


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def cross_entropy(logits: np.ndarray, y: np.ndarray, label_smoothing: float = 0.0) -> tuple[float, np.ndarray]:
    n, n_classes = logits.shape
    probs = softmax(logits)
    if label_smoothing > 0:
        targets = np.full_like(probs, label_smoothing / n_classes)
        targets[np.arange(n), y] += 1.0 - label_smoothing
    else:
        targets = np.zeros_like(probs)
        targets[np.arange(n), y] = 1.0
    loss = float(-np.mean(np.sum(targets * np.log(probs + 1e-9), axis=1)))
    dlogits = (probs - targets) / n
    return loss, dlogits


def augment(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Circular time shift + tiny gain jitter (phase and calibration robustness)."""
    out = x.copy()
    if rng.random() < 0.8:
        shift = int(rng.integers(-4, 5))
        if shift:
            out = np.roll(out, shift, axis=1)
    gain = rng.normal(1.0, 0.012, size=(len(out), 1, out.shape[2])).astype(np.float32)
    out *= gain
    out += rng.normal(0.0, 0.004, size=out.shape).astype(np.float32)
    return out.astype(np.float32)
