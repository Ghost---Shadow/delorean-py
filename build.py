"""Build a DeLorean DMC-12.

    blender -b -P build.py
    blender -b -P build.py -- --render
    blender -b -P build.py -- --doors 52 --steer 12 --render --save

Orchestration only: no geometry lives in this file. The scene is fully reset on
every run, so the result does not depend on what was in Blender beforehand.
"""
from __future__ import annotations

import argparse
import os
import sys

import bpy

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _reload_package() -> None:
    """Drop cached modules so an interactive re-exec picks up file edits."""
    for name in [m for m in sys.modules
                 if m == "delorean" or m.startswith("delorean.")]:
        del sys.modules[name]


_reload_package()

from delorean import body as body_mod          # noqa: E402
from delorean import config as cfg             # noqa: E402
from delorean import doors as doors_mod        # noqa: E402
from delorean import glazing                   # noqa: E402
from delorean import mesh_utils as mu          # noqa: E402
from delorean import validate as validate_mod  # noqa: E402
from delorean import wheels as wheels_mod      # noqa: E402
from delorean.materials import MaterialLibrary, apply_clay_override  # noqa: E402
from delorean.scene import VIEWS, SceneBuilder  # noqa: E402


class DeLoreanBuild:
    """Assembles the whole car, in dependency order."""

    def __init__(self, config: cfg.BuildConfig | None = None) -> None:
        self.cfg = config or cfg.BuildConfig()
        self.materials: MaterialLibrary | None = None
        self.scene: SceneBuilder | None = None
        self.collection: bpy.types.Collection | None = None
        self.parts: dict[str, list[bpy.types.Object]] = {}

    # ------------------------------------------------------------------ setup
    @staticmethod
    def check_blender_version() -> None:
        got = bpy.app.version[:2]
        if got != cfg.REQUIRED_BLENDER:
            raise RuntimeError(
                f"this model targets Blender "
                f"{cfg.REQUIRED_BLENDER[0]}.{cfg.REQUIRED_BLENDER[1]} LTS, "
                f"but is running on {got[0]}.{got[1]}. The Python API moved "
                f"across versions; refusing to build something subtly wrong.")

    def reset(self) -> None:
        """Wipe everything. The build must not depend on prior state."""
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        for coll in list(bpy.data.collections):
            bpy.data.collections.remove(coll)
        for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                      bpy.data.cameras, bpy.data.curves, bpy.data.images,
                      bpy.data.node_groups):
            for item in list(block):
                try:
                    block.remove(item)
                except (RuntimeError, ReferenceError):
                    pass

        self.collection = bpy.data.collections.new(self.cfg.collection_name)
        bpy.context.scene.collection.children.link(self.collection)
        mu.set_target_collection(self.collection)

    # ------------------------------------------------------------------ build
    def run(self) -> "DeLoreanBuild":
        self.check_blender_version()
        self.reset()

        self.materials = MaterialLibrary()
        self.scene = SceneBuilder(self.materials, self.cfg)

        shell = body_mod.BodyBuilder(self.materials).build()

        # order matters: the doors are cut out of the closed shell, then the
        # remaining greenhouse apertures are opened in what is left
        doors = doors_mod.build_doors(shell, self.materials, self.cfg.rig)
        glazing.cut_apertures(shell)

        body_mod.zone_body_materials(shell, self.materials)
        mu.shade_smooth(shell, 32)

        self.parts = {
            "body": [shell],
            "doors": doors,
            "glazing": glazing.build_glazing(self.materials, doors),
            "wheels": wheels_mod.build_wheels(self.materials, self.cfg.rig),
        }

        if self.cfg.build_scene:
            self.scene.build()
        if self.cfg.clay:
            apply_clay_override(self.materials, self.all_parts)

        mu.sync()
        if self.cfg.validate:
            print(validate_mod.validate(self.all_parts, self.cfg.rig,
                                        strict=False).render())
        return self

    @property
    def all_parts(self) -> list[bpy.types.Object]:
        return [ob for group in self.parts.values() for ob in group]

    # ----------------------------------------------------------------- output
    def render_views(self, names: list[str], out_dir: str = "renders") -> list[str]:
        from delorean import preview
        written = []
        for name in names:
            self.scene.apply_view(name)
            path = os.path.join(_ROOT, out_dir, f"{name}.png")
            written.append(preview.render(path, resolution=self.cfg.resolution,
                                          samples=self.cfg.samples))
            print(f"  rendered {name} -> {os.path.relpath(written[-1], _ROOT)}")
        return written

    def save(self, path: str = "delorean.blend") -> str:
        full = os.path.join(_ROOT, path)
        bpy.ops.wm.save_as_mainfile(filepath=full)
        return full


# --------------------------------------------------------------------- entry
def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="build.py")
    ap.add_argument("--doors", type=float, default=0.0,
                    help="gullwing opening angle in degrees")
    ap.add_argument("--steer", type=float, default=0.0,
                    help="front wheel steering angle in degrees")
    ap.add_argument("--clay", action="store_true",
                    help="flat grey override, for shape-only renders")
    ap.add_argument("--environment", choices=("reference", "procedural"),
                    default="reference")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--views", default="hero_front_left,hero_rear_right,side",
                    help="comma-separated view names")
    ap.add_argument("--resolution", default="1600x900")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--save", action="store_true", help="write delorean.blend")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> DeLoreanBuild:
    args = parse_args(argv or [])
    w, _, h = args.resolution.partition("x")

    build = DeLoreanBuild(cfg.BuildConfig(
        rig=cfg.RigConfig(door_angle_deg=args.doors, steer_deg=args.steer),
        clay=args.clay,
        environment=args.environment,
        resolution=(int(w), int(h)),
        samples=args.samples,
    )).run()

    if args.render:
        names = [v.strip() for v in args.views.split(",") if v.strip() in VIEWS]
        build.render_views(names)
    if args.save:
        print(f"  saved {build.save()}")
    return build


def _cli_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


if __name__ == "__main__":
    main(_cli_args())
