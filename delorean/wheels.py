"""Tyres and the DMC-12 turbine alloy wheel.

Reference: references/parts/wheels/wheel-front-turbine.png

The wheel is a dished disc carrying a dense field of thin radial spokes that
run from a raised hub out to a polished outer lip. The hub itself sits proud,
with five exposed lug nuts around a small centre cap. Front and rear share the
design at 14 and 15 inches.
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix

from . import config as cfg
from . import mesh_utils as mu
from .config import WheelSpec

TAU = math.tau


class WheelBuilder:
    """Builds one corner: tyre + rim, both centred on the origin, axis = Y."""

    #: radial spoke count, as counted off the reference crop
    SPOKES = 44
    #: spoke field runs between these fractions of the bead radius
    SPOKE_INNER_F = 0.355
    SPOKE_OUTER_F = 0.895
    #: fraction of the angular pitch each spoke fills. The reference shows the
    #: fins slightly narrower than the grooves between them.
    SPOKE_DUTY = 0.23
    #: hub face and centre cap, as fractions of the bead radius
    HUB_FACE_R = 0.335
    HUB_CAP_R = 0.130
    LUG_CIRCLE_R = 0.215
    #: polished lip, as a fraction of the bead radius
    LIP_INNER_F = 0.90

    def __init__(self, materials) -> None:
        self.materials = materials

    # ------------------------------------------------------------------ tyre
    def tyre(self, name: str, spec: WheelSpec, segments: int = 64) -> bpy.types.Object:
        r, w, bead = spec.radius, spec.width / 2.0, spec.bead_radius
        # radius, axial offset — inner bead round to the tread and back
        side = r - bead                      # sidewall height
        profile = [
            (bead,               -w * 0.62),
            (bead + side * 0.20, -w * 0.92),
            (bead + side * 0.50, -w * 1.00),   # widest point, low on the wall
            (bead + side * 0.86, -w * 0.99),
            (r - 0.004,          -w * 0.93),   # shoulder, deliberately tight
            (r,                  -w * 0.855),
            (r,                  -w * 0.45),
            (r,                   w * 0.45),   # flat tread band
            (r,                   w * 0.855),
            (r - 0.004,           w * 0.93),
            (bead + side * 0.86,  w * 0.99),
            (bead + side * 0.50,  w * 1.00),
            (bead + side * 0.20,  w * 0.92),
            (bead,                w * 0.62),
        ]
        ob = mu.lathe(name, profile, steps=segments)
        mu.set_material(ob, self.materials["tyre"])
        # tight enough to keep the tread shoulders as visible creases
        mu.shade_smooth(ob, 26)
        return ob

    # ------------------------------------------------------------------- rim
    def rim(self, name: str, spec: WheelSpec) -> bpy.types.Object:
        bead, w = spec.bead_radius, spec.width / 2.0
        bm = bmesh.new()

        self._barrel(bm, bead, spec.width)
        self._backing(bm, bead, w)
        self._lip(bm, bead, w)
        self._spokes(bm, bead, w)

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        ob = mu.obj_from_bmesh(name, bm)
        mu.set_material(ob, self.materials["alloy"])
        mu.shade_smooth(ob, 35)

        hub = self._hub(name + "_Hub", bead, w)
        ob = mu.join(name, [ob, hub])
        return ob

    # Axial layout of the rim, as fractions of the tyre's half-width. The wheel
    # is dished: the well floor sits well inboard, the spokes climb out of it,
    # and the polished lip is the frontmost thing on the car.
    BARREL_INNER_F = -0.66
    BARREL_OUTER_F = -0.08
    WELL_FLOOR_F = -0.05
    LIP_FACE_F = 0.52
    SPOKE_HUB_F = 0.14
    SPOKE_RIM_F = 0.50
    HUB_FACE_F = 0.30

    @classmethod
    def _barrel(cls, bm, bead: float, width: float) -> None:
        """Closes the tyre's bore from behind.

        It must stop short of the wheel face: a barrel centred on the axle puts
        its outboard cap in the middle of the spoke field and hides the lot.
        """
        w = width / 2.0
        inner, outer = w * cls.BARREL_INNER_F, w * cls.BARREL_OUTER_F
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=64,
            radius1=bead * 0.995, radius2=bead * 0.995,
            depth=outer - inner,
            matrix=Matrix.Translation((0, (inner + outer) / 2.0, 0))
            @ Matrix.Rotation(math.radians(90), 4, 'X'))

    @classmethod
    def _backing(cls, bm, bead: float, w: float) -> None:
        """The floor of the rim well, seen in the gaps between the spokes."""
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=48,
            radius1=bead * cls.LIP_INNER_F, radius2=bead * cls.LIP_INNER_F,
            depth=0.010,
            matrix=Matrix.Translation((0, w * cls.WELL_FLOOR_F, 0))
            @ Matrix.Rotation(math.radians(90), 4, 'X'))

    def _lip(self, bm, bead: float, w: float) -> None:
        """Polished outer rim flange, rolled over at the tyre bead."""
        r_out, r_in = bead * 0.995, bead * self.LIP_INNER_F
        y_face = w * self.LIP_FACE_F
        segs = 96
        cols = []
        for k in range(segs):
            a = TAU * k / segs
            ca, sa = math.cos(a), math.sin(a)
            cols.append((
                bm.verts.new((r_out * ca, y_face,         r_out * sa)),
                bm.verts.new((r_in * ca,  y_face - 0.012, r_in * sa)),
                bm.verts.new((r_in * ca,  w * self.WELL_FLOOR_F, r_in * sa)),
            ))
        for k in range(segs):
            a, b = cols[k], cols[(k + 1) % segs]
            bm.faces.new((a[0], b[0], b[1], a[1]))
            bm.faces.new((a[1], b[1], b[2], a[2]))

    def _spokes(self, bm, bead: float, w: float) -> None:
        """Thin radial fins, dished inward toward the hub."""
        r0 = bead * self.SPOKE_INNER_F
        r1 = bead * self.SPOKE_OUTER_F
        y0 = w * self.SPOKE_HUB_F              # hub end sits deeper
        y1 = w * self.SPOKE_RIM_F              # rim end meets the lip
        thickness = 0.011
        half = self.SPOKE_DUTY * (TAU / self.SPOKES)

        for k in range(self.SPOKES):
            a = TAU * k / self.SPOKES
            corners = []
            for radius, y in ((r0, y0), (r1, y1)):
                for da in (-half, half):
                    ca, sa = math.cos(a + da), math.sin(a + da)
                    corners.append((
                        bm.verts.new((radius * ca, y, radius * sa)),
                        bm.verts.new((radius * ca, y - thickness, radius * sa)),
                    ))
            inner_a, inner_b, outer_a, outer_b = corners
            bm.faces.new((inner_a[0], inner_b[0], outer_b[0], outer_a[0]))
            bm.faces.new((outer_a[1], outer_b[1], inner_b[1], inner_a[1]))
            bm.faces.new((inner_a[0], outer_a[0], outer_a[1], inner_a[1]))
            bm.faces.new((outer_b[0], inner_b[0], inner_b[1], outer_b[1]))
            bm.faces.new((outer_a[0], outer_b[0], outer_b[1], outer_a[1]))

    def _hub(self, name: str, bead: float, w: float) -> bpy.types.Object:
        """Raised hub face, five lug nuts, centre cap."""
        parts: list[bpy.types.Object] = []
        y_face = w * self.HUB_FACE_F

        face = mu.cone(name + "_Face", bead * self.HUB_FACE_R,
                       bead * (self.HUB_FACE_R - 0.035), 0.030,
                       location=(0, y_face - 0.015, 0), axis="Y", segments=44)
        mu.set_material(face, self.materials["alloy"])
        parts.append(face)

        stud_r = bead * self.LUG_CIRCLE_R
        for k in range(5):
            a = TAU * k / 5 + math.radians(18)
            nut = mu.cone(f"{name}_Lug{k}", 0.0105, 0.0098, 0.019,
                          location=(stud_r * math.cos(a), y_face + 0.010,
                                    stud_r * math.sin(a)),
                          axis="Y", segments=6)
            mu.set_material(nut, self.materials["steel_dark"])
            parts.append(nut)

        cap = mu.cone(name + "_Cap", bead * self.HUB_CAP_R,
                      bead * (self.HUB_CAP_R - 0.014), 0.016,
                      location=(0, y_face + 0.010, 0), axis="Y", segments=32)
        mu.set_material(cap, self.materials["black_gloss"])
        parts.append(cap)

        hub = mu.join(name, parts)
        mu.shade_smooth(hub, 30)
        return hub

    # ----------------------------------------------------------------- corner
    def corner(self, tag: str, spec: WheelSpec, location: tuple[float, float, float],
               mirrored: bool) -> list[bpy.types.Object]:
        tyre = self.tyre(f"Wheel_{tag}_Tyre", spec)
        rim = self.rim(f"Wheel_{tag}_Rim", spec)
        for ob in (tyre, rim):
            ob.location = location
            if mirrored:
                ob.scale = (1.0, -1.0, 1.0)
        return [tyre, rim]


def build_wheels(materials, rig: cfg.RigConfig) -> list[bpy.types.Object]:
    """All four corners, positioned on the axles and posed by `rig`."""
    builder = WheelBuilder(materials)
    out: list[bpy.types.Object] = []

    layout = (
        ("FL", cfg.WHEEL_FRONT, cfg.FRONT_AXLE_X,  cfg.HALF_TRACK_FRONT, False),
        ("FR", cfg.WHEEL_FRONT, cfg.FRONT_AXLE_X, -cfg.HALF_TRACK_FRONT, True),
        ("RL", cfg.WHEEL_REAR,  cfg.REAR_AXLE_X,   cfg.HALF_TRACK_REAR,  False),
        ("RR", cfg.WHEEL_REAR,  cfg.REAR_AXLE_X,  -cfg.HALF_TRACK_REAR,  True),
    )

    for tag, spec, x, y, mirrored in layout:
        parts = builder.corner(tag, spec, (x, y, spec.radius), mirrored)
        steered = tag.startswith("F")
        for ob in parts:
            rot_y = math.radians(rig.wheel_spin_deg)
            rot_z = math.radians(rig.steer_deg) if steered else 0.0
            ob.rotation_euler = (0.0, rot_y, rot_z)
        out.extend(parts)
    mu.sync()
    return out
