"""Generate car silhouette masks for the scored reference photographs.

Backgrounds dominate Canny — foliage, stone, gravel, rust — so a reference is
only usable for scoring once there is a mask beside it saying which pixels are
car. Masks are generated from a committed spec (`references/masks.json`) so the
result is reproducible rather than hand-painted, and the PNGs are committed so
scoring needs neither this tool nor a working OpenCV.

    python tools/make_masks.py
    python tools/make_masks.py --only studio
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "references"
OUT = REFS / "masks"
SPEC = REFS / "masks.json"


def _clean(mask: np.ndarray, close: int = 9) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask = np.where(labels == biggest, 255, 0).astype(np.uint8)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(mask)
    cv2.drawContours(filled, contours, -1, 255, cv2.FILLED)
    return filled


def by_grabcut(img: np.ndarray, box: list[float], iterations: int = 6) -> np.ndarray:
    """Foreground extraction seeded by a rectangle around the car."""
    h, w = img.shape[:2]
    rect = (int(box[0] * w), int(box[1] * h),
            int((box[2] - box[0]) * w), int((box[3] - box[1]) * h))
    mask = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask, rect, bgd, fgd, iterations, cv2.GC_INIT_WITH_RECT)
    binary = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0)
    return _clean(binary.astype(np.uint8))


def by_backdrop(img: np.ndarray, box: list[float],
                tolerance: int = 60) -> np.ndarray:
    """For a studio shot: anything far from the backdrop colour is the car."""
    h, w = img.shape[:2]
    p = max(6, min(h, w) // 30)
    corners = np.concatenate([
        img[:p, :p].reshape(-1, 3), img[:p, -p:].reshape(-1, 3),
        img[-p:, :p].reshape(-1, 3), img[-p:, -p:].reshape(-1, 3)])
    backdrop = np.median(corners, axis=0)

    distance = np.linalg.norm(img.astype(np.int16) - backdrop, axis=2)
    mask = ((distance > tolerance) * 255).astype(np.uint8)

    # nothing outside the seed box can be car
    keep = np.zeros_like(mask)
    keep[int(box[1] * h):int(box[3] * h), int(box[0] * w):int(box[2] * w)] = 255
    return _clean(cv2.bitwise_and(mask, keep))


def by_neutral(img: np.ndarray, box: list[float], saturation: int = 62,
               iterations: int = 5) -> np.ndarray:
    """For a studio shot on a coloured backdrop.

    The DMC-12 is bare steel, so it is close to neutral grey, while the
    backdrop and the floor it stands on are strongly coloured. Separating on
    saturation therefore cuts the car out cleanly *and* drops the floor, which
    a plain colour-distance threshold keeps (the floor is the same blue as the
    wall, just darker).

    The result then seeds a GrabCut pass, which recovers the tinted shadow
    side of the car that pure saturation misses.
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    neutral = (hsv[..., 1] < saturation).astype(np.uint8) * 255

    inside = np.zeros((h, w), np.uint8)
    inside[int(box[1] * h):int(box[3] * h), int(box[0] * w):int(box[2] * w)] = 255
    seed = cv2.bitwise_and(neutral, inside)
    seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    seed = _clean(seed)
    if np.count_nonzero(seed) < 0.02 * seed.size:
        return seed

    gc = np.full((h, w), cv2.GC_BGD, np.uint8)
    gc[inside > 0] = cv2.GC_PR_BGD
    gc[seed > 0] = cv2.GC_PR_FGD
    core = cv2.erode(seed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    gc[core > 0] = cv2.GC_FGD

    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, gc, None, bgd, fgd, iterations, cv2.GC_INIT_WITH_MASK)
    out = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0)
    return _clean(out.astype(np.uint8))


def by_bands(img: np.ndarray, box: list[float], bg_top: float = 0.0,
             bg_bottom: float = 1.0, bg_left: float = 0.0,
             bg_right: float = 1.0, iterations: int = 6) -> np.ndarray:
    """GrabCut given explicit strips of known background.

    A rectangle-seeded GrabCut fails when the car fills the frame: almost every
    pixel is inside the rectangle, so the algorithm has nearly no background to
    build a colour model from and happily labels the gravel as car. Naming the
    strips that are definitely *not* car — sky above, road below, margins at
    the sides — gives it something to learn from.
    """
    h, w = img.shape[:2]
    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)

    x0, y0, x1, y1 = (int(box[0] * w), int(box[1] * h),
                      int(box[2] * w), int(box[3] * h))
    gc[y0:y1, x0:x1] = cv2.GC_PR_FGD

    gc[:int(bg_top * h), :] = cv2.GC_BGD
    gc[int(bg_bottom * h):, :] = cv2.GC_BGD
    gc[:, :int(bg_left * w)] = cv2.GC_BGD
    gc[:, int(bg_right * w):] = cv2.GC_BGD

    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, gc, None, bgd, fgd, iterations, cv2.GC_INIT_WITH_MASK)
    out = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0)
    return _clean(out.astype(np.uint8))


METHODS = {"grabcut": by_grabcut, "backdrop": by_backdrop,
           "neutral": by_neutral, "bands": by_bands}


def build(entry: dict) -> tuple[str, float]:
    src = REFS / entry["src"]
    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(src)

    fn = METHODS[entry.get("method", "grabcut")]
    kwargs = {k: v for k, v in entry.items()
              if k in ("tolerance", "iterations", "saturation",
                       "bg_top", "bg_bottom", "bg_left", "bg_right")}
    mask = fn(img, entry["box"], **kwargs)

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / (Path(entry["src"]).stem + ".png")
    cv2.imwrite(str(dst), mask)

    coverage = float(np.count_nonzero(mask)) / mask.size
    return str(dst.relative_to(ROOT)), coverage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    entries = json.loads(SPEC.read_text())["masks"]
    for entry in entries:
        if args.only and args.only.lower() not in entry["src"].lower():
            continue
        path, coverage = build(entry)
        flag = "" if 0.10 < coverage < 0.80 else "   <-- check this"
        print(f"{entry['src']:<44} {entry.get('method', 'grabcut'):<9} "
              f"covers {coverage * 100:5.1f}%  -> {path}{flag}")


if __name__ == "__main__":
    main()
