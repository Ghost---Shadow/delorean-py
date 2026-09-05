"""Render the model as line art with a transparent background.

Runs inside Blender. The companion `metrics/overlay_edges.py` composites the
result over a Canny edge map of the reference photograph, which is how camera
mismatch and misproportion are told apart by eye.

    blender -b -P metrics/render_wireframe.py -- --reference front-quarter-left-gravel
    blender -b -P metrics/render_wireframe.py -- --reference rear-quarter-right-doors-open \\
        --azimuth 325 --elevation 13 --lens 78 --distance 11 --door-angle 52

Camera, in order of precedence: any explicit `--azimuth/--elevation/--lens/
--distance/--target-z` override, then `--view <name>` from `scene.VIEWS`, then
the reference's committed `.camera.json`, then `hero_front_left`. Overrides
compose with whichever base is chosen, so a solved camera can be nudged one
axis at a time.

The aspect ratio is taken from the reference image itself. Comparing a 16:9
render against a 3:2 photograph stretches one axis and invents a proportion
error that is not in the model.
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

REFERENCE_DIR = os.path.join(_ROOT, "references")
CAMERA_DIR = os.path.join(REFERENCE_DIR, "cameras")
OUT_DIR = os.path.join(_ROOT, "renders", "metrics")


def find_reference(stem: str) -> str | None:
    for ext in (".jpg", ".jpeg", ".png", ".JPG"):
        candidate = os.path.join(REFERENCE_DIR, stem + ext)
        if os.path.exists(candidate):
            return candidate
    return None


def reference_aspect(stem: str, fallback: float = 0.6667) -> float:
    """height / width of the reference, read from the file."""
    path = find_reference(stem)
    if path is None:
        return fallback
    image = bpy.data.images.load(path, check_existing=True)
    w, h = image.size
    bpy.data.images.remove(image)
    return (h / w) if w else fallback


def solved_camera(stem: str) -> dict | None:
    path = os.path.join(CAMERA_DIR, stem + ".camera.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _flat(name: str, value: float) -> bpy.types.Material:
    """An emission shader, so the result owes nothing to lighting."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (value, value, value, 1.0)
    emit.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def wireframe_settings(scn, thickness: float, xray: bool) -> None:
    """Turn every mesh into a true wireframe: black edges on white.

    Not Workbench. Its WIREFRAME shading looks right in the viewport and is
    unusable in a final render: the lines are never written into alpha (so
    `film_transparent` gives a blank image), and `wireframe_color_type` —
    THEME / OBJECT / RANDOM — takes in the viewport but not in a render, where
    the lines always come out one level off the background whatever it is set
    to. Freestyle would work but needs line-set state kept deterministic and
    costs an order of magnitude more time.

    So the wireframe is built as geometry instead. A Wireframe modifier turns
    every edge into a solid tube, `material_offset` paints those tubes black
    while the original surfaces stay white, and the surfaces then occlude the
    tubes behind them. That is hidden-line removal for free, which is what
    makes this comparable to a Canny map of a photograph — where you also only
    see the near side of the car. `--xray` drops the surfaces to show every
    edge instead.

    Thickness is in metres, so a line is a fixed size on the car rather than
    a fixed size on screen, and it stays honest when the distance changes.
    """
    scn.render.engine = 'BLENDER_EEVEE'
    scn.render.film_transparent = False
    # Standard, not AgX: a tone map designed to keep highlights pleasant puts
    # emissive white at about 196/255 and lifts black off the floor, which is
    # the last thing a line drawing wants.
    scn.view_settings.view_transform = 'Standard'
    scn.view_settings.look = 'None'
    scn.view_settings.exposure = 0.0
    scn.view_settings.gamma = 1.0

    white = _flat("WF_Surface", 1.0)
    black = _flat("WF_Line", 0.0)

    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scn.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs["Background"],
                 nt.nodes.new("ShaderNodeOutputWorld").inputs["Surface"])

    for ob in [o for o in bpy.data.objects if o.type == 'MESH']:
        if ob.name == "Ground":
            ob.hide_render = True
            continue
        ob.data.materials.clear()
        ob.data.materials.append(white)
        ob.data.materials.append(black)
        for poly in ob.data.polygons:
            poly.material_index = 0

        md = ob.modifiers.new("wireframe", 'WIREFRAME')
        md.thickness = thickness
        # outward. The default offset buries the tubes inside the surface they
        # trace, and the render comes back a blank white field.
        md.offset = 1.0
        md.use_boundary = True
        md.use_replace = xray          # x-ray drops the occluding surfaces
        md.use_even_offset = False
        md.material_offset = 1


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="render_wireframe")
    ap.add_argument("--reference", required=True,
                    help="reference stem, for the aspect ratio and any "
                         "committed camera solve")
    ap.add_argument("--view", default=None,
                    help="named view from delorean.scene.VIEWS")
    ap.add_argument("--azimuth", type=float, default=None)
    ap.add_argument("--elevation", type=float, default=None)
    ap.add_argument("--distance", type=float, default=None)
    ap.add_argument("--lens", type=float, default=None)
    ap.add_argument("--target-z", type=float, default=None)
    ap.add_argument("--door-angle", type=float, default=None)
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--thickness", type=float, default=0.004,
                    help="line thickness in metres, on the car not on screen")
    ap.add_argument("--xray", action="store_true",
                    help="draw edges hidden behind the bodywork too")
    ap.add_argument("--interior", action="store_true",
                    help="include the cabin; off by default because in "
                         "wireframe it reads as noise inside the silhouette")
    ap.add_argument("--suffix", default="wire")
    args = ap.parse_args(argv)

    import build as bld
    from delorean import config as cfg, preview
    from delorean.scene import VIEWS, View

    solved = solved_camera(args.reference)

    if args.view:
        base = VIEWS[args.view]
    elif solved:
        base = View(azimuth=solved["azimuth"], elevation=solved["elevation"],
                    distance=solved["distance"], lens=solved["lens"],
                    target=(0.0, 0.0, solved.get("target_z", 0.62)))
    else:
        base = VIEWS["hero_front_left"]

    target_z = (args.target_z if args.target_z is not None else base.target[2])
    view = View(
        azimuth=args.azimuth if args.azimuth is not None else base.azimuth,
        elevation=(args.elevation if args.elevation is not None
                   else base.elevation),
        distance=args.distance if args.distance is not None else base.distance,
        lens=args.lens if args.lens is not None else base.lens,
        target=(0.0, 0.0, target_z))

    door_angle = args.door_angle
    if door_angle is None:
        door_angle = (solved or {}).get("door_angle_deg", 0.0)

    aspect = reference_aspect(args.reference)
    height = max(2, int(round(args.width * aspect)))

    build = bld.DeLoreanBuild(cfg.BuildConfig(
        rig=cfg.RigConfig(door_angle_deg=door_angle),
        engine="eevee", samples=1, clay=True, validate=False,
        build_interior=args.interior, environment="procedural",
        resolution=(args.width, height),
    )).run()
    build.scene.apply_view(view)

    wireframe_settings(bpy.context.scene, args.thickness, args.xray)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{args.reference}.{args.suffix}.png")
    preview.render(path, resolution=(args.width, height), samples=1)

    print(f"\n  wireframe   -> {os.path.relpath(path, _ROOT)}")
    print(f"  camera       azimuth {view.azimuth:.1f}  elevation "
          f"{view.elevation:.1f}  lens {view.lens:.1f} mm  distance "
          f"{view.distance:.2f} m  target_z {target_z:.2f}")
    print(f"  doors        {door_angle:.1f} deg")
    print(f"  resolution   {args.width} x {height}  (aspect {aspect:.4f}, "
          f"from the reference)\n")

    # hand the camera back so overlay_edges.py can record what it is showing
    with open(os.path.join(OUT_DIR, f"{args.reference}.{args.suffix}.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"reference": args.reference, "azimuth": view.azimuth,
                   "elevation": view.elevation, "lens": view.lens,
                   "distance": view.distance, "target_z": target_z,
                   "door_angle_deg": door_angle,
                   "width": args.width, "height": height}, fh, indent=2)


def _cli_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


if __name__ == "__main__":
    main(_cli_args())
