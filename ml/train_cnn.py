"""Train the NumPy 1D-CNN and export firmware weights.

Run:
    python -m ml.train_cnn --per-class 600 --epochs 30
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .cnn import Adam, CNN1D, augment, cross_entropy
from .config import (
    CLASSES,
    CONFUSION_MATRIX_PATH,
    CONV1_FILTERS,
    I_SCALE,
    METRICS_PATH,
    MODEL_CARD_PATH,
    N_CLASSES,
    PROCESSED_DIR,
    SEED,
    TRAIN_FRACTION,
    TRAINING_CURVE_PATH,
    VAL_FRACTION,
    V_SCALE,
    WEIGHTS_PATH,
    WINDOW,
)
from .dataset import make_dataset, save_dataset, stratified_split


def accuracy(model: CNN1D, x: np.ndarray, y: np.ndarray, batch: int = 256) -> float:
    correct = 0
    for start in range(0, len(x), batch):
        pred = model.predict(x[start : start + batch])
        correct += int((pred == y[start : start + batch]).sum())
    return correct / max(len(x), 1)


def evaluate(model: CNN1D, x: np.ndarray, y: np.ndarray) -> dict:
    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    probs = model.predict_proba(x)
    pred = probs.argmax(axis=1)
    labels = list(range(N_CLASSES))
    cm = confusion_matrix(y, pred, labels=labels)
    report = classification_report(
        y, pred, labels=labels, target_names=list(CLASSES), output_dict=True, zero_division=0
    )
    return {
        "accuracy": float((pred == y).mean()),
        "macro_f1": float(f1_score(y, pred, average="macro")),
        "weighted_f1": float(f1_score(y, pred, average="weighted")),
        "per_class": {
            name: {
                "precision": float(report[name]["precision"]),
                "recall": float(report[name]["recall"]),
                "f1": float(report[name]["f1-score"]),
                "support": int(report[name]["support"]),
            }
            for name in CLASSES
        },
        "confusion_matrix": cm.tolist(),
        "mean_confidence": float(probs.max(axis=1).mean()),
    }


def plot_confusion(cm: np.ndarray, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 5.4), dpi=150)
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(N_CLASSES), labels=CLASSES, rotation=35, ha="right")
    ax.set_yticks(range(N_CLASSES), labels=CLASSES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("GridShield 1D-CNN — held-out test set")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=8,
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_curves(history: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), dpi=150)
    axes[0].plot(history["train_loss"], label="train")
    axes[0].plot(history["val_loss"], label="validation")
    axes[0].set_title("Cross-entropy loss")
    axes[0].set_xlabel("epoch")
    axes[0].legend()
    axes[1].plot(history["train_acc"], label="train")
    axes[1].plot(history["val_acc"], label="validation")
    axes[1].set_title("Accuracy")
    axes[1].set_xlabel("epoch")
    axes[1].set_ylim(0, 1.02)
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def train(args: argparse.Namespace) -> dict:
    rng = np.random.default_rng(args.seed)

    dataset_path = PROCESSED_DIR / "pqd_dataset.npz"
    if args.reuse_dataset and dataset_path.exists():
        data = np.load(dataset_path)
        X, y = data["X"], data["y"]
        print(f"reused dataset {dataset_path} ({len(X)} windows)")
    else:
        print(f"generating {args.per_class} windows/class ...")
        X, y, waves = make_dataset(n_per_class=args.per_class, seed=args.seed)
        save_dataset(dataset_path, X, y, waves)
        print(f"saved {dataset_path}")

    x_train, y_train, x_val, y_val, x_test, y_test = stratified_split(
        X, y, TRAIN_FRACTION, VAL_FRACTION, seed=args.seed
    )
    print(f"split: train={len(x_train)} val={len(x_val)} test={len(x_test)}")

    model = CNN1D.initialise(seed=args.seed)
    params = model.state()
    optimiser = Adam(params, lr=args.lr)
    # Keep the optimiser and model pointing at the same arrays.
    model.W1, model.b1 = params["W1"], params["b1"]
    model.W2, model.b2 = params["W2"], params["b2"]
    model.W3, model.b3 = params["W3"], params["b3"]
    model.W4, model.b4 = params["W4"], params["b4"]

    history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
    best_val = -1.0
    best_state = model.state()
    patience = 0
    batch_size = args.batch_size
    n_batches = max(1, len(x_train) // batch_size)
    total_steps = max(1, args.epochs * n_batches)
    step = 0

    started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        order = rng.permutation(len(x_train))
        epoch_loss = 0.0
        for b in range(n_batches):
            idx = order[b * batch_size : (b + 1) * batch_size]
            xb = augment(x_train[idx], rng)
            yb = y_train[idx]
            logits = model.forward(xb, cache=True)
            loss, dlogits = cross_entropy(logits, yb, label_smoothing=0.03)
            grads = model.backward(dlogits)
            lr = args.lr * (0.05 + 0.95 * 0.5 * (1 + np.cos(np.pi * step / total_steps)))
            optimiser.step(grads, lr=lr)
            epoch_loss += loss
            step += 1
            if step % 40 == 0:
                print(f"  epoch {epoch:02d} step {step:04d}/{total_steps} loss {loss:.4f}", flush=True)

        train_acc = accuracy(model, x_train[:600], y_train[:600])
        val_acc = accuracy(model, x_val, y_val)
        val_logits = model.forward(x_val)
        val_loss, _ = cross_entropy(val_logits, y_val)
        history["train_loss"].append(epoch_loss / n_batches)
        history["val_loss"].append(float(val_loss))
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)
        print(
            f"epoch {epoch:02d}/{args.epochs} loss {epoch_loss / n_batches:.4f} "
            f"val_loss {val_loss:.4f} train_acc {train_acc:.4f} val_acc {val_acc:.4f}",
            flush=True,
        )

        if val_acc > best_val + 1e-4:
            best_val = val_acc
            best_state = model.state()
            patience = 0
        else:
            patience += 1
            if patience >= args.patience:
                print(f"early stopping at epoch {epoch} (best val acc {best_val:.4f})")
                break

    for key, value in best_state.items():
        setattr(model, key, value)

    train_seconds = time.perf_counter() - started
    test_metrics = evaluate(model, x_test, y_test)
    val_metrics = evaluate(model, x_val, y_val)

    # Host-side latency (NumPy, not the ESP32; documented separately).
    sample = x_test[:1]
    timings = []
    for _ in range(30):
        t0 = time.perf_counter()
        model.predict_proba(sample)
        timings.append((time.perf_counter() - t0) * 1000.0)

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test": test_metrics,
        "validation": val_metrics,
        "training": {
            "per_class": args.per_class,
            "epochs_requested": args.epochs,
            "epochs_run": len(history["train_loss"]),
            "batch_size": batch_size,
            "learning_rate": args.lr,
            "best_val_accuracy": best_val,
            "seconds": round(train_seconds, 2),
            "seed": args.seed,
        },
        "params": model.n_params,
        "host_inference_ms_median": round(float(np.median(timings)), 3),
        "note": (
            "Metrics are on a synthetic, noise-augmented dataset. They do not "
            "constitute validation on recorded grid waveforms."
        ),
    }

    model.save(WEIGHTS_PATH, extra={
        "v_scale": V_SCALE,
        "i_scale": I_SCALE,
        "metrics": test_metrics,
    })

    model_card = {
        "name": "GridShield PQD 1D-CNN",
        "version": "1.0.0",
        "created_at": metrics["generated_at"],
        "framework": "NumPy reference implementation (TFLite export optional)",
        "input": {
            "shape": [WINDOW, 2],
            "channels": ["voltage_pu", "load_current_pu"],
            "v_scale_volts": V_SCALE,
            "i_scale_amps": I_SCALE,
            "sample_rate_hz": 2000,
            "window_ms": WINDOW / 2000 * 1000,
        },
        "architecture": {
            "conv1": {"filters": CONV1_FILTERS, "kernel": 5, "activation": "relu"},
            "pool1": 2,
            "conv2": {"filters": 16, "kernel": 3, "activation": "relu"},
            "pool2": 2,
            "global_pool": "concat(mean, max)",
            "dense": [32, N_CLASSES],
            "parameters": model.n_params,
        },
        "classes": list(CLASSES),
        "metrics": test_metrics,
        "training": metrics["training"],
        "intended_use": "Research prototype for edge power-quality classification.",
        "limitations": [
            "Trained on synthetic waveforms; field validation is required.",
            "Weight-only int8 quantisation in firmware (activations remain fp32).",
            "Not a certified protection device; never replace an MCB/RCD.",
        ],
    }
    MODEL_CARD_PATH.write_text(json.dumps(model_card, indent=2), encoding="utf-8")
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    plot_curves(history, TRAINING_CURVE_PATH)
    plot_confusion(np.asarray(test_metrics["confusion_matrix"]), CONFUSION_MATRIX_PATH)

    from .export_c_header import export_header

    export_header(model, class_names=list(CLASSES), path=None, verify_x=x_test, verify_y=y_test)

    print("\n=== held-out test metrics ===")
    print(f"accuracy : {test_metrics['accuracy']:.4f}")
    print(f"macro F1 : {test_metrics['macro_f1']:.4f}")
    for name in CLASSES:
        row = test_metrics["per_class"][name]
        print(f"  {name:26s} P={row['precision']:.3f} R={row['recall']:.3f} F1={row['f1']:.3f}")
    print(f"weights  : {WEIGHTS_PATH}")
    print(f"firmware : {Path(__file__).resolve().parents[1] / 'firmware/arduino/gridshield_node/model_weights.h'}")
    return metrics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-class", type=int, default=600)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--reuse-dataset", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    train(parse_args())
