"""Bumpers' small furniture: louvres, mirrors, badges and exhaust.

Reference: references/parts/trim/louvres-backlight.png (the rear louvre, by
far the most recognisable piece), plus mirror-door.png, grille-dmc-badge.png,
rear-bumper-badge.png and exhaust-tips.png.

Every piece here is a thin appliance sitting *on* a surface someone else
built (the roof/fastback skin from `body.skin_point`, the flanks from
`body.flank_half_width`), never a cut into it — trim is bolted on, not
moulded in. That is also why nothing here needs a boolean: it is all just
small solids placed against a surface that is already known.

The louvre slats are the one piece worth explaining. A real DMC-12 louvre is
a single moulded shade, but modelling it as N separate tilted plates reads
better under a studio light: each slat gets its own tiny highlight and cast
shadow, which is what makes the assembly look slatted rather than like a
single ribbed lump. Each slat's tilt is derived from the local slope of the
roof skin at its position, not a fixed angle, so the whole run continues to
follow the fastback if the body's station table ever changes.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

from . import config as cfg
from . import mesh_utils as mu
from .body import flank_half_width, skin_point

Vec3 = tuple[float, float, float]


class TrimBuilder:
    """Builds every non-structural appliance: louvres, mirrors, badges, exhaust."""

    # ------------------------------------------------------------- louvres
    #: the backlight aperture runs x=0.470..1.395 (glazing.BACKLIGHT_PLAN) —
    #: the louvre sits directly over it, so it shares that footprint
    LOUVRE_X0 = 0.470
    LOUVRE_X1 = 1.395
    #: slat count, off the reference crop: 12, comfortably in the 11-13 range
    LOUVRE_SLAT_COUNT = 12
    #: how far toward the roof edge (u=1 in skin_point terms) the slats reach;
    #: kept just inside the backlight glass patch (which stops at 0.905) so
    #: the louvre never overhangs bare steel
    LOUVRE_U = 0.90
    #: fraction of each slat's pitch that is solid plate; the rest is the gap
    #: you see daylight (or rusty wall) through in the reference
    LOUVRE_DUTY = 0.62
    LOUVRE_THICKNESS = 0.012
    #: lift above the skin — clears the backlight glass, which is itself
    #: inset 17 mm into the same surface
    LOUVRE_Z_OFFSET = 0.040
    LOUVRE_RAIL_WIDTH = 0.028
    LOUVRE_RAIL_SEGMENTS = 6
    LOUVRE_FRAME_THICKNESS = 0.022

    # -------------------------------------------------------------- mirror
    #: base of the A-pillar / top-front corner of the door, where the stalk
    #: actually meets sheet metal (see trim.py module tests for how this was
    #: probed against the body's station table)
    MIRROR_X = -0.80
    MIRROR_Z = 0.80
    MIRROR_STALK_LEN = 0.045
    MIRROR_STALK_SECTION = 0.028

    # -------------------------------------------------------------- badges
    GRILLE_TEXT = "DMC"
    GRILLE_SIZE = 0.028
    GRILLE_EXTRUDE = 0.004
    GRILLE_Z = 0.47

    REAR_TEXT = "DE LOREAN"
    REAR_SIZE = 0.030
    REAR_EXTRUDE = 0.004
    REAR_Z = 0.42
    #: offset toward the driver's (left, +Y) side, as in the reference crop
    REAR_Y_OFFSET = 0.38

    # ------------------------------------------------------------- exhaust
    EXHAUST_X = 2.05
    EXHAUST_Y = 0.34
    EXHAUST_Z = 0.20
    EXHAUST_SIZE = (0.11, 0.050, 0.038)
    EXHAUST_TILT_DEG = -8.0

    # ---------------------------------------------------------- lic. plate
    PLATE_X = cfg.LENGTH / 2.0 - 0.006
    PLATE_Z = 0.50
    PLATE_SIZE = (0.010, 0.300, 0.150)

    def __init__(self, materials) -> None:
        self.materials = materials

    # =====================================================================
    #  louvres
    # =====================================================================
    def louvres(self) -> list[bpy.types.Object]:
        mat = self.materials["black_matte"]
        slats = self._louvre_slats(mat)
        rail_l = self._rail("Trim_Louvre_RailL", self.LOUVRE_X0, self.LOUVRE_X1,
                            self.LOUVRE_U, self.LOUVRE_RAIL_SEGMENTS,
                            self.LOUVRE_RAIL_WIDTH, self.LOUVRE_THICKNESS * 1.4,
                            self.LOUVRE_Z_OFFSET + 0.004, mat)
        rail_r = mu.mirror_object_y(rail_l, "Trim_Louvre_RailR")
        frame_top = self._frame_bar("Trim_Louvre_FrameTop", self.LOUVRE_X0,
                                    self.LOUVRE_Z_OFFSET + 0.006, mat)
        frame_bottom = self._frame_bar("Trim_Louvre_FrameBottom", self.LOUVRE_X1,
                                       self.LOUVRE_Z_OFFSET + 0.006, mat)
        return [*slats, rail_l, rail_r, frame_top, frame_bottom]

    def _louvre_slats(self, mat: bpy.types.Material) -> list[bpy.types.Object]:
        x0, x1, n = self.LOUVRE_X0, self.LOUVRE_X1, self.LOUVRE_SLAT_COUNT
        pitch = (x1 - x0) / n
        slats = []
        for i in range(n):
            x_start = x0 + i * pitch
            x_end = x_start + pitch * self.LOUVRE_DUTY
            x_c = (x_start + x_end) / 2.0

            dx = x_end - x_start
            dz = skin_point(x_end, 0.0)[2] - skin_point(x_start, 0.0)[2]
            depth = math.hypot(dx, dz)
            angle = -math.atan2(dz, dx)

            half_w = skin_point(x_c, self.LOUVRE_U)[1]
            z_c = skin_point(x_c, 0.0)[2]

            ob = mu.box(f"Trim_Louvre_Slat_{i:02d}",
                       (depth, 2.0 * half_w, self.LOUVRE_THICKNESS),
                       location=(x_c, 0.0, z_c + self.LOUVRE_Z_OFFSET))
            ob.rotation_euler = (0.0, angle, 0.0)
            mu.set_material(ob, mat)
            slats.append(ob)
        return slats

    @staticmethod
    def _rail(name: str, x0: float, x1: float, u: float, n: int,
             width: float, thickness: float, z_off: float,
             mat: bpy.types.Material) -> bpy.types.Object:
        """A strip that follows the skin's curvature, as a chain of short
        tilted plates — the same trick as the slats, just laid end to end."""
        xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
        pts = [skin_point(x, u) for x in xs]
        segs = []
        for i in range(n):
            p0, p1 = pts[i], pts[i + 1]
            dx, dz = p1[0] - p0[0], p1[2] - p0[2]
            length = math.hypot(dx, dz)
            angle = -math.atan2(dz, dx)
            seg = mu.box(f"{name}_seg{i}", (length, width, thickness),
                        location=((p0[0] + p1[0]) / 2.0,
                                 (p0[1] + p1[1]) / 2.0,
                                 (p0[2] + p1[2]) / 2.0 + z_off))
            seg.rotation_euler = (0.0, angle, 0.0)
            segs.append(seg)
        rail = mu.join(name, segs)
        mu.set_material(rail, mat)
        return rail

    def _frame_bar(self, name: str, x: float, z_off: float,
                  mat: bpy.types.Material) -> bpy.types.Object:
        """The rail across the top or bottom of the louvre assembly."""
        half_w = skin_point(x, self.LOUVRE_U)[1] * 1.06
        z_c = skin_point(x, 0.0)[2]
        h = 0.01
        dz = skin_point(x + h, 0.0)[2] - skin_point(x - h, 0.0)[2]
        angle = -math.atan2(dz, 2.0 * h)

        ob = mu.box(name, (self.LOUVRE_FRAME_THICKNESS * 1.4, 2.0 * half_w,
                          self.LOUVRE_FRAME_THICKNESS),
                   location=(x, 0.0, z_c + z_off))
        ob.rotation_euler = (0.0, angle, 0.0)
        mu.set_material(ob, mat)
        return ob

    # =====================================================================
    #  door mirrors
    # =====================================================================
    def mirrors(self) -> list[bpy.types.Object]:
        x, z = self.MIRROR_X, self.MIRROR_Z
        y_body = flank_half_width(x, z)
        body_mat = self.materials["black"]
        glass_mat = self.materials["chrome"]

        y_head = y_body + self.MIRROR_STALK_LEN
        stalk = mu.box("Trim_Mirror_Stalk", (self.MIRROR_STALK_SECTION,
                                            self.MIRROR_STALK_LEN,
                                            self.MIRROR_STALK_SECTION),
                       location=(x, (y_body + y_head) / 2.0, z))
        mu.set_material(stalk, body_mat)

        # a wedge housing, narrow at the leading (nose-ward) edge and full
        # depth at the trailing edge — see mirror-door.png
        housing_poly = [
            (x - 0.050, y_head + 0.000),
            (x + 0.015, y_head + 0.000),
            (x + 0.060, y_head + 0.050),
            (x + 0.028, y_head + 0.090),
            (x - 0.028, y_head + 0.090),
            (x - 0.058, y_head + 0.045),
        ]
        housing = mu.prism("Trim_Mirror_Housing", housing_poly,
                          z - 0.032, z + 0.032, axis="Z")
        mu.set_material(housing, body_mat)

        glass = mu.box("Trim_Mirror_Glass", (0.006, 0.075, 0.045),
                       location=(x + 0.034, y_head + 0.050, z))
        mu.set_material(glass, glass_mat)

        left = mu.join("Trim_Mirror_L", [stalk, housing, glass])
        mu.shade_smooth(left, 25)
        right = mu.mirror_object_y(left, "Trim_Mirror_R")
        return [left, right]

    # =====================================================================
    #  text badges
    # =====================================================================
    def _text_badge(self, name: str, text: str, size: float, extrude: float,
                    location: Vec3, normal: Vec3, up: Vec3,
                    mat: bpy.types.Material) -> bpy.types.Object:
        """A small extruded FONT badge, converted to mesh before it is handed
        back — the validator inspects polygons, and a curve has none."""
        n = Vector(normal).normalized()
        u = Vector(up).normalized()
        right = u.cross(n).normalized()

        curve = bpy.data.curves.new(name + "Curve", type='FONT')
        curve.body = text
        curve.size = size
        curve.extrude = extrude
        curve.align_x = 'CENTER'
        curve.align_y = 'CENTER'

        ob = bpy.data.objects.new(name, curve)
        mu.link(ob)
        ob.location = location

        rot = Matrix.Identity(3)
        rot.col[0] = right
        rot.col[1] = u
        rot.col[2] = n
        ob.rotation_euler = rot.to_4x4().to_euler()

        mu.sync()
        mu.activate(ob)
        bpy.ops.object.convert(target='MESH')
        mu.set_material(ob, mat)
        return ob

    def grille_badge(self) -> list[bpy.types.Object]:
        """The "DMC" badge, small and centred low on the nose fascia."""
        x = -cfg.LENGTH / 2.0 - 0.004
        ob = self._text_badge(
            "Trim_GrilleBadge", self.GRILLE_TEXT, self.GRILLE_SIZE,
            self.GRILLE_EXTRUDE, (x, 0.0, self.GRILLE_Z),
            normal=(-1.0, 0.0, 0.0), up=(0.0, 0.0, 1.0),
            mat=self.materials["chrome"])
        return [ob]

    def rear_badge(self) -> list[bpy.types.Object]:
        """The "DE LOREAN" badge, offset to the driver's side of the tail."""
        x = cfg.LENGTH / 2.0 + 0.004
        ob = self._text_badge(
            "Trim_RearBadge", self.REAR_TEXT, self.REAR_SIZE,
            self.REAR_EXTRUDE, (x, self.REAR_Y_OFFSET, self.REAR_Z),
            normal=(1.0, 0.0, 0.0), up=(0.0, 0.0, 1.0),
            mat=self.materials["chrome"])
        return [ob]

    # =====================================================================
    #  exhaust tips
    # =====================================================================
    def exhaust_tips(self) -> list[bpy.types.Object]:
        mat = self.materials["steel_dark"]
        left = mu.box("Trim_Exhaust_L", self.EXHAUST_SIZE,
                      location=(self.EXHAUST_X, self.EXHAUST_Y, self.EXHAUST_Z))
        left.rotation_euler = (0.0, math.radians(self.EXHAUST_TILT_DEG), 0.0)
        mu.set_material(left, mat)
        right = mu.mirror_object_y(left, "Trim_Exhaust_R")
        return [left, right]

    # =====================================================================
    #  rear licence plate
    # =====================================================================
    def rear_plate(self) -> list[bpy.types.Object]:
        plate = mu.box("Trim_RearPlate", self.PLATE_SIZE,
                       location=(self.PLATE_X, 0.0, self.PLATE_Z))
        mu.set_material(plate, self.materials["black_gloss"])
        return [plate]

    # =====================================================================
    #  everything
    # =====================================================================
    def build(self) -> list[bpy.types.Object]:
        out: list[bpy.types.Object] = []
        out += self.louvres()
        out += self.mirrors()
        out += self.grille_badge()
        out += self.rear_badge()
        out += self.exhaust_tips()
        out += self.rear_plate()
        mu.sync()
        return out


def build_trim(materials) -> list[bpy.types.Object]:
    """All trim: louvres, mirrors, badges and exhaust."""
    return TrimBuilder(materials).build()
