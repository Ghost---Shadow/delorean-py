"""Composite the model's wireframe over a Canny edge map of the reference.

Runs in system Python, outside Blender. Produce the wireframe first:

    blender -b -P metrics/render_wireframe.py -- --reference <stem> [camera args]
    python -m metrics.overlay_edges --reference <stem>

Two images come out, and they answer different questions.

`<stem>.overlay.png` draws both at their true positions. It shows whether the
**camera** matches: if the wireframe sits somewhere else in frame, or is a
different size, the pose is wrong and nothing about the model's shape can be
read off it yet.

`<stem>.overlay-fit.png` scales the wireframe **uniformly** and slides it so
its bounding box shares a centre and a width with the reference's. That takes
framing out of the picture and leaves proportion. The scale is deliberately
uniform: stretching each axis to fit would erase the very error the overlay
exists to show. So after fitting, a height that overshoots or falls short is a
real proportion error, and the printed aspect figures put a number on it.

Canny fires on gravel, foliage and brickwork as readily as on bodywork, so a
committed mask in `references/masks/` is used when one exists. Without it the
background is included and mostly measures scenery.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from metrics.edges import canny, clean_mask, load_gray
else:
    from .edges import canny, clean_mask, load_gray

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "references"
MASKS = REFS / "masks"
RENDERS = ROOT / "renders" / "metrics"
OUT = ROOT / "metrics" / "out"

#: BGR. The reference is the ground truth, so it gets the calm colour; the
#: model is what is under examination, so it gets the loud one.
COLOUR_REFERENCE = (205, 205, 205)
COLOUR_MODEL = (60, 60, 255)
COLOUR_AGREE = (90, 255, 120)


def find_reference(stem: str) -> Path:
    for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG"):
        candidate = REFS / (stem + ext)
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no reference image for {stem!r} in {REFS}")


def wireframe_ink(path: Path, size: tuple[int, int]) -> np.ndarray:
    """Line intensity 0..255 from a dark-on-white wireframe render."""
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(
            f"{path} — render it with metrics/render_wireframe.py first")
    if (gray.shape[1], gray.shape[0]) != size:
        gray = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
    return (255 - gray).astype(np.uint8)


def reference_edges(stem: str, size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray | None]:
    """Canny of the reference, masked to the car when a mask is committed."""
    path = find_reference(stem)
    gray = load_gray(path, width=size[0])
    if (gray.shape[1], gray.shape[0]) != size:
        gray = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)

    edge = canny(gray)
    mask = None
    mask_path = MASKS / (stem + ".png")
    if mask_path.exists():
        m = load_gray(mask_path, width=size[0])
        if (m.shape[1], m.shape[0]) != size:
            m = cv2.resize(m, size, interpolation=cv2.INTER_NEAREST)
        mask = clean_mask(((m > 127) * 255).astype(np.uint8))
        edge = cv2.bitwise_and(edge, mask)
    return edge, mask


def bbox(binary: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(binary)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def fit_uniform(ink: np.ndarray, src: tuple, dst: tuple,
                size: tuple[int, int]) -> tuple[np.ndarray, float]:
    """Uniform scale + translate so `src` box matches `dst` box in width."""
    sx0, sy0, sx1, sy1 = src
    dx0, dy0, dx1, dy1 = dst
    src_w = max(1, sx1 - sx0)
    scale = (dx1 - dx0) / src_w

    src_cx, src_cy = (sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0
    dst_cx, dst_cy = (dx0 + dx1) / 2.0, (dy0 + dy1) / 2.0
    matrix = np.array([[scale, 0.0, dst_cx - scale * src_cx],
                       [0.0, scale, dst_cy - scale * src_cy]], dtype=np.float32)
    warped = cv2.warpAffine(ink, matrix, size, flags=cv2.INTER_LINEAR,
                            borderValue=0)
    return warped, scale


def composite(ref_edge: np.ndarray, model_ink: np.ndarray,
              ghost: np.ndarray | None = None,
              model_threshold: int = 40) -> np.ndarray:
    """Reference edges in grey, model wireframe in red, agreement in green."""
    h, w = ref_edge.shape[:2]
    out = np.zeros((h, w, 3), dtype=np.uint8)

    if ghost is not None:
        out = (cv2.cvtColor(ghost, cv2.COLOR_GRAY2BGR) * 0.22).astype(np.uint8)

    ref_on = ref_edge > 0
    for c in range(3):
        out[:, :, c] = np.where(ref_on, COLOUR_REFERENCE[c], out[:, :, c])

    alpha = np.clip(model_ink.astype(np.float32) / 200.0, 0.0, 1.0)[..., None]
    model_on = model_ink > model_threshold
    colour = np.zeros_like(out)
    near_ref = cv2.dilate(ref_edge, np.ones((3, 3), np.uint8), iterations=1) > 0
    for c in range(3):
        colour[:, :, c] = np.where(model_on & near_ref, COLOUR_AGREE[c],
                                   COLOUR_MODEL[c])
    out = (out * (1.0 - alpha) + colour * alpha).astype(np.uint8)
    return out


def annotate(img: np.ndarray, lines: list[str]) -> np.ndarray:
    y = 22
    for text in lines:
        cv2.putText(img, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (255, 255, 255), 1, cv2.LINE_AA)
        y += 20
    return img


def run(stem: str, suffix: str = "wire", ghost: bool = False) -> int:
    render = RENDERS / f"{stem}.{suffix}.png"
    gray_render = cv2.imread(str(render), cv2.IMREAD_GRAYSCALE)
    if gray_render is None:
        print(f"  no wireframe at {render.relative_to(ROOT)}\n"
              f"  blender -b -P metrics/render_wireframe.py -- "
              f"--reference {stem}")
        return 1
    size = (gray_render.shape[1], gray_render.shape[0])

    model_ink = wireframe_ink(render, size)
    ref_edge, ref_mask = reference_edges(stem, size)
    ghost_img = load_gray(find_reference(stem), width=size[0]) if ghost else None
    if ghost_img is not None and (ghost_img.shape[1], ghost_img.shape[0]) != size:
        ghost_img = cv2.resize(ghost_img, size, interpolation=cv2.INTER_AREA)

    OUT.mkdir(parents=True, exist_ok=True)

    camera = {}
    camera_path = RENDERS / f"{stem}.{suffix}.json"
    if camera_path.exists():
        camera = json.loads(camera_path.read_text(encoding="utf-8"))

    header = [f"{stem}"]
    if camera:
        header.append(
            f"az {camera['azimuth']:.0f}  el {camera['elevation']:.0f}  "
            f"lens {camera['lens']:.0f}mm  d {camera['distance']:.1f}m  "
            f"doors {camera.get('door_angle_deg', 0):.0f}deg")

    raw = composite(ref_edge, model_ink, ghost_img)
    annotate(raw, header + ["as rendered - shows CAMERA mismatch"])
    raw_path = OUT / f"{stem}.overlay.png"
    cv2.imwrite(str(raw_path), raw)

    # ---- fitted
    ref_area = ref_mask if ref_mask is not None else (ref_edge > 0).astype(np.uint8) * 255
    dst = bbox(ref_area)
    src = bbox((model_ink > 40).astype(np.uint8))
    if dst is None or src is None:
        print("  cannot fit: one of the two silhouettes is empty")
        return 1

    fitted, scale = fit_uniform(model_ink, src, dst, size)
    ref_w, ref_h = dst[2] - dst[0], dst[3] - dst[1]
    mod_w, mod_h = src[2] - src[0], src[3] - src[1]
    ref_aspect = ref_h / max(1, ref_w)
    mod_aspect = mod_h / max(1, mod_w)
    error = 100.0 * (mod_aspect - ref_aspect) / ref_aspect

    fit_img = composite(ref_edge, fitted, ghost_img)
    annotate(fit_img, header + [
        "uniform-fit to reference width - shows PROPORTION",
        f"ref {ref_w}x{ref_h} px  aspect {ref_aspect:.3f}",
        f"model {mod_w}x{mod_h} px  aspect {mod_aspect:.3f}  "
        f"({error:+.1f}% tall)"])
    fit_path = OUT / f"{stem}.overlay-fit.png"
    cv2.imwrite(str(fit_path), fit_img)

    print(f"\n  {stem}")
    if camera:
        print(f"      camera     az {camera['azimuth']:.1f}  el "
              f"{camera['elevation']:.1f}  lens {camera['lens']:.1f} mm  "
              f"distance {camera['distance']:.2f} m")
    print(f"      reference  {ref_w} x {ref_h} px   aspect {ref_aspect:.4f}"
          + ("" if ref_mask is not None else "   [no mask - Canny includes "
                                             "the background]"))
    print(f"      model      {mod_w} x {mod_h} px   aspect {mod_aspect:.4f}"
          f"   fitted at {scale:.3f}x")
    print(f"      silhouette is {error:+.1f}% too {'tall' if error > 0 else 'short'}"
          f" for its width")
    print(f"      -> {raw_path.relative_to(ROOT)}")
    print(f"      -> {fit_path.relative_to(ROOT)}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="metrics.overlay_edges")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--suffix", default="wire")
    ap.add_argument("--ghost", action="store_true",
                    help="dim the photograph underneath, for orientation")
    args = ap.parse_args()
    return run(args.reference, args.suffix, args.ghost)


if __name__ == "__main__":
    raise SystemExit(main())
