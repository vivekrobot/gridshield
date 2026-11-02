"""Export trained weights to a compact C header for the ESP32.

Weights are symmetrically quantised per tensor to int8 (one scale factor per
matrix).  Biases stay float32 because they are few and quantising them adds
error for no meaningful flash saving.  The firmware dequantises on the fly
(``w = q * scale``), so inference is fp32 with int8 storage — the same
"weight-only quantisation" trick used by many microcontrollers.

The header is a plain C file with no external dependencies, which is why the
firmware can build even on a machine without TensorFlow Lite Micro installed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .cnn import CNN1D
from .config import C_HEADER_PATH, CLASSES, I_SCALE, V_SCALE, WEIGHTS_PATH

WEIGHT_KEYS = ("W1", "W2", "W3", "W4")
ARRAY_NAMES = {
    "W1": "kConv1W",
    "W2": "kConv2W",
    "W3": "kDense1W",
    "W4": "kDense2W",
}


def quantise(w: np.ndarray) -> tuple[np.ndarray, float]:
    max_abs = float(np.max(np.abs(w)))
    if max_abs < 1e-12:
        return np.zeros_like(w, dtype=np.int8), 1.0
    scale = max_abs / 127.0
    q = np.clip(np.rint(w / scale), -127, 127).astype(np.int8)
    return q, scale


def dequantise(q: np.ndarray, scale: float) -> np.ndarray:
    return (q.astype(np.float32) * scale).astype(np.float32)


def _format_int8(q: np.ndarray) -> str:
    flat = q.reshape(-1)
    lines = []
    per_line = 24
    for start in range(0, len(flat), per_line):
        chunk = ", ".join(str(int(v)) for v in flat[start : start + per_line])
        lines.append("    " + chunk + ",")
    return "\n".join(lines)


def _cfloat(value: float, digits: int = 9) -> str:
    """Format a valid C++ float literal (``0`` is not a float literal)."""
    text = f"{float(value):.{digits}g}"
    if "." not in text and "e" not in text and "E" not in text:
        text += ".0"
    return text + "f"


def _format_float(arr: np.ndarray) -> str:
    flat = arr.reshape(-1)
    lines = []
    per_line = 6
    for start in range(0, len(flat), per_line):
        chunk = ", ".join(_cfloat(v) for v in flat[start : start + per_line])
        lines.append("    " + chunk + ",")
    return "\n".join(lines)


def export_header(
    model: CNN1D,
    class_names: list[str] | None = None,
    path: str | Path | None = None,
    verify_x: np.ndarray | None = None,
    verify_y: np.ndarray | None = None,
) -> Path:
    class_names = class_names or list(CLASSES)
    path = Path(path) if path is not None else C_HEADER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    quantised: dict[str, tuple[np.ndarray, float]] = {}
    for key in WEIGHT_KEYS:
        quantised[key] = quantise(getattr(model, key))

    # Optional parity check: dequantised model must match the fp32 model.
    parity = None
    if verify_x is not None and len(verify_x):
        clone = CNN1D.load(WEIGHTS_PATH) if WEIGHTS_PATH.exists() else model
        for key in WEIGHT_KEYS:
            q, scale = quantised[key]
            setattr(clone, key, dequantise(q, scale))
        if verify_y is not None:
            x = verify_x[: min(500, len(verify_x))]
            y = verify_y[: len(x)]
            parity = float((clone.predict(x) == y).mean())
        agreement = float((clone.predict(verify_x[:500]) == model.predict(verify_x[:500])).mean())
        parity = agreement

    def arr(values: np.ndarray, ctype: str) -> str:
        if ctype == "int8":
            return _format_int8(values)
        return _format_float(values)

    lines: list[str] = []
    lines.append("// AUTO-GENERATED FILE — do not edit by hand.")
    lines.append("// Source: ml/export_c_header.py")
    lines.append("// Weights: symmetric per-tensor int8 quantisation, fp32 biases.")
    lines.append("#pragma once")
    lines.append("")
    lines.append("#include <stdint.h>")
    lines.append("")
    lines.append("#define GS_MODEL_INPUT_LEN 160")
    lines.append("#define GS_MODEL_N_CHANNELS 2")
    lines.append(f"#define GS_MODEL_N_CLASSES {len(class_names)}")
    lines.append("#define GS_CONV1_FILTERS 8")
    lines.append("#define GS_CONV1_KERNEL 5")
    lines.append("#define GS_CONV2_FILTERS 16")
    lines.append("#define GS_CONV2_KERNEL 3")
    lines.append("#define GS_POOL_SIZE 2")
    lines.append("#define GS_DENSE_UNITS 32")
    lines.append("#define GS_L1 156")
    lines.append("#define GS_L2 76")
    lines.append("#define GS_L3 38")
    lines.append("")
    lines.append(f"static const float kInputVoltScale = {V_SCALE:.6f}f;")
    lines.append(f"static const float kInputAmpScale = {I_SCALE:.6f}f;")
    if parity is not None:
        lines.append(f"// dequantised-vs-fp32 prediction parity on the test subset: {parity:.4f}")
    lines.append("")
    lines.append("static const char* const kClassNames[GS_MODEL_N_CLASSES] = {")
    for name in class_names:
        lines.append(f'    "{name}",')
    lines.append("};")
    lines.append("")

    for key, cname in ARRAY_NAMES.items():
        q, scale = quantised[key]
        lines.append(f"static const int8_t {cname}[] = {{")
        lines.append(arr(q, "int8"))
        lines.append("};")
        lines.append(f"static const float {cname}Scale = {_cfloat(scale, 12)};")
        lines.append("")

    for key, cname in (("b1", "kConv1B"), ("b2", "kConv2B"), ("b3", "kDense1B"), ("b4", "kDense2B")):
        values = getattr(model, key)
        lines.append(f"static const float {cname}[] = {{")
        lines.append(arr(values, "float"))
        lines.append("};")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    size_kb = path.stat().st_size / 1024
    print(f"wrote {path} ({size_kb:.1f} KB, {model.n_params} params, parity={parity})")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, default=WEIGHTS_PATH)
    parser.add_argument("--out", type=Path, default=C_HEADER_PATH)
    args = parser.parse_args(argv)
    model = CNN1D.load(args.weights)
    export_header(model, path=args.out)


if __name__ == "__main__":
    main()
