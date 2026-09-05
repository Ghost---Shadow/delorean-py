"""Generate per-part reference crops from references/crops.json.

Each module of the model has a matching close-up reference so that isolated
renders can be compared against a like-for-like photograph instead of the whole
car. Boxes are normalised, so re-exporting a source at a different resolution
does not invalidate the spec.

    python tools/crop_references.py [--min-width 512]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "references"
OUT = REFS / "parts"
SPEC = REFS / "crops.json"


def load_spec() -> list[dict]:
    return json.loads(SPEC.read_text())["crops"]


def crop_one(entry: dict, min_width: int) -> tuple[str, tuple[int, int]]:
    src = REFS / entry["src"]
    img = cv2.imread(str(src))
    if img is None:
        raise FileNotFoundError(f"cannot read {src}")

    h, w = img.shape[:2]
    x0, y0, x1, y1 = entry["box"]
    px = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    if px[2] <= px[0] or px[3] <= px[1]:
        raise ValueError(f"{entry['name']}: degenerate box {entry['box']}")

    out = img[px[1]:px[3], px[0]:px[2]]
    if out.shape[1] < min_width:
        scale = min_width / out.shape[1]
        out = cv2.resize(out, (min_width, int(out.shape[0] * scale)),
                         interpolation=cv2.INTER_CUBIC)

    dst = OUT / entry["part"] / f"{entry['name']}.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), out)
    return str(dst.relative_to(ROOT)), (out.shape[1], out.shape[0])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-width", type=int, default=512,
                    help="upscale crops narrower than this")
    args = ap.parse_args()

    for entry in load_spec():
        path, (w, h) = crop_one(entry, args.min_width)
        print(f"{entry['part']:<10} {entry['name']:<24} {w:>5}x{h:<5} -> {path}")


if __name__ == "__main__":
    main()
