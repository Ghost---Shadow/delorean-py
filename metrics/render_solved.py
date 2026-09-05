"""Render the model from a solved camera, for scoring.

Runs inside Blender. Writes a clay pass (flat grey, fixed lights) at the
reference's own aspect ratio, so the comparison measures shape and not shading.

    blender -b -P metrics/render_solved.py -- --reference front-quarter-left-gravel
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import bpy

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

CAMERA_DIR = os.path.join(_ROOT, "references", "cameras")
OUT_DIR = os.path.join(_ROOT, "renders", "metrics")


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True)
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--silhouette", action="store_true",
                    help="also write an alpha-only silhouette pass")
    args = ap.parse_args(argv)

    with open(os.path.join(CAMERA_DIR, args.reference + ".camera.json"),
              encoding="utf-8") as fh:
        solved = json.load(fh)

    import build as bld
    from delorean import config as cfg, preview
    from delorean.scene import View

    aspect = solved.get("aspect", 0.6667)
    height = max(2, int(round(args.width * aspect)))

    build = bld.DeLoreanBuild(cfg.BuildConfig(
        rig=cfg.RigConfig(door_angle_deg=solved.get("door_angle_deg", 0.0)),
        engine="eevee", samples=32, clay=True, validate=False,
        environment="procedural", resolution=(args.width, height),
    )).run()

    build.scene.apply_view(View(
        azimuth=solved["azimuth"], elevation=solved["elevation"],
        distance=solved["distance"], lens=solved["lens"],
        target=(0.0, 0.0, solved.get("target_z", 0.62))))

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, args.reference + ".png")
    preview.render(path, resolution=(args.width, height), samples=32)
    print(f"  rendered -> {os.path.relpath(path, _ROOT)}")

    if args.silhouette:
        r = bpy.context.scene.render
        was = r.film_transparent
        r.film_transparent = True
        sil = os.path.join(OUT_DIR, args.reference + ".alpha.png")
        preview.render(sil, resolution=(args.width, height), samples=8)
        r.film_transparent = was
        print(f"  silhouette -> {os.path.relpath(sil, _ROOT)}")


if __name__ == "__main__":
    cli = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(cli)
