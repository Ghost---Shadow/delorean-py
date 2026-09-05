"""Solve the camera pose that matches a reference photograph.

Comparing a render to a photograph measures *camera mismatch* until the two
cameras agree. Rather than guess focal length and pose by eye, this searches
for them: render a silhouette, score it against the reference mask, keep the
best.

The search is over azimuth, elevation and focal length only. Distance and
framing are removed beforehand by cropping both silhouettes to their bounding
boxes and normalising scale — so the search covers exactly the parameters that
change the *shape* of the projection, and nothing that merely moves the camera
closer. Distance is recovered afterwards from the fitted bounding box.

Runs inside Blender (it has to render). Uses numpy only — no OpenCV, because
Blender's bundled interpreter is not to be pip-polluted.

    blender -b -P metrics/solve_camera.py -- --reference front-quarter-left-gravel
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict

import bpy
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MASK_DIR = os.path.join(_ROOT, "references", "masks")
SOLVE_DIR = os.path.join(_ROOT, "references", "cameras")


# --------------------------------------------------------------------- images
def load_mask(path: str) -> np.ndarray:
    """A committed mask PNG as a boolean array, origin top-left."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return np.flipud(px[..., 0]) > 0.5


def render_silhouette(width: int = 320) -> np.ndarray:
    """Render the current camera and return the alpha channel as a mask.

    Rendering with a transparent film gives a perfect silhouette for free —
    no thresholding, no background colour to guess.
    """
    scn = bpy.context.scene
    r = scn.render
    saved = (r.resolution_x, r.resolution_y, r.film_transparent, r.filepath)

    aspect = saved[1] / saved[0] if saved[0] else 0.5625
    r.resolution_x = width
    r.resolution_y = max(2, int(round(width * aspect)))
    r.film_transparent = True
    r.filepath = os.path.join(SOLVE_DIR, "_solve_tmp.png")
    os.makedirs(SOLVE_DIR, exist_ok=True)
    try:
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(r.filepath, check_existing=False)
        w, h = img.size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
        bpy.data.images.remove(img)
        return np.flipud(px[..., 3]) > 0.5
    finally:
        (r.resolution_x, r.resolution_y, r.film_transparent, r.filepath) = saved


# ------------------------------------------------------------------- scoring
def bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return None
    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    return int(x0), int(y0), int(x1) + 1, int(y1) + 1


def _resize_nearest(mask: np.ndarray, w: int, h: int) -> np.ndarray:
    ys = (np.arange(h) * mask.shape[0] / h).astype(np.int32).clip(0, mask.shape[0] - 1)
    xs = (np.arange(w) * mask.shape[1] / w).astype(np.int32).clip(0, mask.shape[1] - 1)
    return mask[ys][:, xs]


def normalised_iou(reference: np.ndarray, render: np.ndarray,
                   size: int = 256) -> float:
    """IoU after cropping to bounding boxes and matching scale, aspect kept.

    Blind to distance and to where the car sits in frame — those are framing,
    not shape, and letting them into the search finds a camera that is wrong
    in an interesting new way.

    Emphatically *not* blind to aspect ratio. Squashing both silhouettes into
    a square normalises away the single strongest shape cue there is: do that
    and the solver cheerfully reports a near-side-on telephoto view as the
    best match for a three-quarter photograph, because once both are square
    they genuinely do overlap better.
    """
    ba, bb = bbox(reference), bbox(render)
    if ba is None or bb is None:
        return 0.0

    a = reference[ba[1]:ba[3], ba[0]:ba[2]]
    b = render[bb[1]:bb[3], bb[0]:bb[2]]

    # scale each by its own width, so each keeps its own height
    def fit(m: np.ndarray) -> np.ndarray:
        w = size
        h = max(1, int(round(m.shape[0] * size / m.shape[1])))
        return _resize_nearest(m, w, h)

    a, b = fit(a), fit(b)

    canvas_h = max(a.shape[0], b.shape[0])
    out = []
    for m in (a, b):
        pad = np.zeros((canvas_h, size), dtype=bool)
        top = (canvas_h - m.shape[0]) // 2          # align on centre of mass
        pad[top:top + m.shape[0], :] = m
        out.append(pad)

    union = np.count_nonzero(out[0] | out[1])
    return float(np.count_nonzero(out[0] & out[1])) / union if union else 0.0


# --------------------------------------------------------------------- solve
@dataclass
class Solution:
    reference: str
    azimuth: float
    elevation: float
    lens: float
    distance: float
    target_z: float
    iou: float
    door_angle_deg: float
    render_width: int
    aspect: float = 0.6667


class CameraSolver:
    def __init__(self, scene_builder, reference_mask: np.ndarray,
                 width: int = 320) -> None:
        self.scene = scene_builder
        self.reference = reference_mask
        self.width = width
        self._cache: dict[tuple, float] = {}

    def score(self, azimuth: float, elevation: float, lens: float,
              target_z: float = 0.62) -> float:
        key = (round(azimuth, 2), round(elevation, 2), round(lens, 2),
               round(target_z, 3))
        if key in self._cache:
            return self._cache[key]

        from delorean.scene import View
        self.scene.apply_view(View(azimuth=azimuth, elevation=elevation,
                                   distance=11.0, lens=lens,
                                   target=(0.0, 0.0, target_z)))
        value = normalised_iou(self.reference, render_silhouette(self.width))
        self._cache[key] = value
        return value

    def search(self, azimuths, elevations, lenses, target_z=0.62):
        best, best_score = None, -1.0
        for az in azimuths:
            for el in elevations:
                for lens in lenses:
                    s = self.score(az, el, lens, target_z)
                    if s > best_score:
                        best, best_score = (az, el, lens), s
        return best, best_score

    def solve(self, azimuth_range=(0.0, 350.0),
              elevation_range=(0.0, 34.0),
              lens_range=(28.0, 180.0)) -> tuple[tuple, float]:
        """Sweep the whole circle, then refine around the winner.

        Deliberately not seeded with a guess at which way the car is facing.
        A narrow range around the wrong azimuth converges happily onto a
        mirror image and reports a plausible-looking number.
        """
        az = np.arange(azimuth_range[0], azimuth_range[1] + 1e-6, 10.0)
        el = np.arange(elevation_range[0], elevation_range[1] + 1e-6, 8.0)
        lens = np.array([35.0, 60.0, 95.0, 145.0])
        best, score = self.search(az, el, lens)
        print(f"    coarse  az {best[0]:6.1f}  el {best[1]:5.1f}  "
              f"lens {best[2]:6.1f}  IoU {score:.4f}")

        # keep the global best: a refinement pass can land on a worse point
        # than the one it started from, and silently returning that undoes the
        # whole search
        for step, span in ((4.0, 10.0), (1.5, 5.0), (0.5, 2.0)):
            centre = best
            az = np.arange(centre[0] - span, centre[0] + span + 1e-6, step)
            el = np.arange(max(0.0, centre[1] - span),
                           centre[1] + span + 1e-6, step)
            lens = np.linspace(max(lens_range[0], centre[2] * 0.80),
                               min(lens_range[1], centre[2] * 1.25), 5)
            candidate, value = self.search(az, el, lens)
            if value > score:
                best, score = candidate, value
            print(f"    refine  az {best[0]:6.1f}  el {best[1]:5.1f}  "
                  f"lens {best[2]:6.1f}  IoU {score:.4f}")
        return best, score

    def fit_distance(self, azimuth, elevation, lens, target_z=0.62,
                     probe_distance=11.0) -> float:
        """Distance that makes the render's silhouette fill the reference's."""
        from delorean.scene import View
        self.scene.apply_view(View(azimuth=azimuth, elevation=elevation,
                                   distance=probe_distance, lens=lens,
                                   target=(0.0, 0.0, target_z)))
        rendered = render_silhouette(self.width)
        br, bref = bbox(rendered), bbox(self.reference)
        if br is None or bref is None:
            return probe_distance
        # widths as a fraction of their own frame, so resolution cancels
        got = (br[2] - br[0]) / rendered.shape[1]
        want = (bref[2] - bref[0]) / self.reference.shape[1]
        return probe_distance * (got / want) if want else probe_distance


def solve_reference(stem: str, door_angle: float = 0.0,
                    width: int = 320) -> Solution:
    import build as bld
    from delorean import config as cfg

    mask_path = os.path.join(MASK_DIR, stem + ".png")
    if not os.path.exists(mask_path):
        raise FileNotFoundError(
            f"no mask for {stem}; run tools/make_masks.py first")
    reference = load_mask(mask_path)

    build = bld.DeLoreanBuild(cfg.BuildConfig(
        rig=cfg.RigConfig(door_angle_deg=door_angle),
        engine="eevee", samples=4, clay=True, validate=False,
        environment="procedural", resolution=(width, int(width * 0.5625)),
    )).run()

    # aspect ratio must match the reference, or the projection is wrong
    h, w = reference.shape
    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = max(2, int(round(width * h / w)))

    solver = CameraSolver(build.scene, reference, width)
    (az, el, lens), iou = solver.solve()
    distance = solver.fit_distance(az, el, lens)

    solution = Solution(reference=stem, azimuth=float(az), elevation=float(el),
                        lens=float(lens), distance=float(distance),
                        target_z=0.62, iou=float(iou),
                        door_angle_deg=door_angle, render_width=width,
                        aspect=float(h) / float(w))

    os.makedirs(SOLVE_DIR, exist_ok=True)
    out = os.path.join(SOLVE_DIR, stem + ".camera.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(asdict(solution), fh, indent=2)
    print(f"    -> {os.path.relpath(out, _ROOT)}")
    return solution


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True)
    ap.add_argument("--doors", type=float, default=0.0)
    ap.add_argument("--width", type=int, default=320)
    args = ap.parse_args(argv)

    print(f"  solving camera for {args.reference}")
    solve_reference(args.reference, args.doors, args.width)


if __name__ == "__main__":
    cli = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(cli)
