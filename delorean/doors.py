"""Gullwing doors.

Reference: references/parts/doors/door-gullwing-open.png

The doors are not modelled separately and then fitted — they are cut out of the
finished shell. Intersecting a copy of the body with a door-shaped prism gives
a panel that matches its aperture exactly, everywhere, by construction; the
same prism, offset outward by half a shut line, cuts the hole it came from.

A DMC-12 door takes a slice of roof with it, because the torsion-bar hinge sits
on the roof rather than on a pillar. That is why the outline runs all the way
inboard to a narrow centre spine, and why the car keeps a T-bar down the middle
when both doors are up.
"""
from __future__ import annotations

import math

import bpy

from . import config as cfg
from . import mesh_utils as mu

#: Door outline in the XZ plane, swept across the car in Y.
#:   A -> B   front shut line, just behind the cowl
#:   B -> C   up the A-pillar; deliberately clears the windscreen surface by
#:            about 40 mm, which becomes the pillar's width
#:   C -> D   across the roof, above everything, so the cut is a clean vertical
#:   D -> E   rear shut line, raked forward at the top like the real B-pillar
#:   E -> A   sill, sitting just above the black rocker moulding
DOOR_OUTLINE = [
    (-0.965, 0.300),
    (-0.965, 0.790),
    (-0.200, 1.250),
    ( 0.330, 1.250),
    ( 0.430, 0.300),
]

#: How far inboard the door reaches. Between the two doors this leaves the
#: 210 mm centre spine that the real car has.
SPINE_HALF_WIDTH = 0.105
DOOR_OUTBOARD = 1.350

#: Daylight opening — the window aperture cut out of the door panel.
WINDOW_OUTLINE = [
    (-0.855, 0.905),
    (-0.640, 1.010),
    (-0.330, 1.095),
    ( 0.290, 1.098),
    ( 0.352, 0.905),
]

#: Hinge axis: along X, up at the roof, just outboard of the spine.
HINGE_Y = 0.128
HINGE_Z = 1.163


class DoorBuilder:
    """Splits both doors out of a finished body shell."""

    def __init__(self, materials) -> None:
        self.materials = materials

    def split(self, body: bpy.types.Object) -> list[bpy.types.Object]:
        doors = []
        for side, sign in (("L", 1), ("R", -1)):
            doors.append(self._one(body, side, sign))
        return doors

    def _one(self, body: bpy.types.Object, side: str, sign: int) -> bpy.types.Object:
        y_in = sign * SPINE_HALF_WIDTH
        y_out = sign * DOOR_OUTBOARD
        lo, hi = min(y_in, y_out), max(y_in, y_out)

        panel_cutter = mu.prism(f"DoorCut_{side}", DOOR_OUTLINE, lo, hi, axis="Y")

        # the same prism grown by half a shut line, so the aperture is exactly
        # PANEL_GAP wider than the panel on every edge
        gap = cfg.PANEL_GAP / 2.0
        hole_cutter = mu.prism(
            f"DoorHole_{side}", mu.offset_poly(DOOR_OUTLINE, gap),
            lo - (gap if sign > 0 else 0.0),
            hi + (0.0 if sign > 0 else gap), axis="Y")

        door = mu.duplicate(body, f"Door_{side}")
        mu.boolean(door, panel_cutter, 'INTERSECT')
        mu.boolean(body, hole_cutter, 'DIFFERENCE')

        self._cut_window(door, sign)
        self._set_hinge(door, sign)

        from .body import zone_body_materials
        zone_body_materials(door, self.materials)
        mu.shade_smooth(door, 32)
        return door

    @staticmethod
    def _cut_window(door: bpy.types.Object, sign: int) -> None:
        lo, hi = sorted((sign * 0.20, sign * 1.40))
        cutter = mu.prism("WinCut", WINDOW_OUTLINE, lo, hi, axis="Y")
        mu.boolean(door, cutter, 'DIFFERENCE')

    @staticmethod
    def _set_hinge(door: bpy.types.Object, sign: int) -> None:
        """Origin on the hinge axis, so opening is a single X rotation."""
        mu.set_origin(door, (0.0, sign * HINGE_Y, HINGE_Z))


def pose_doors(doors: list[bpy.types.Object], rig: cfg.RigConfig) -> None:
    """Swing the doors up. Left rotates +X, right -X."""
    angle = math.radians(rig.door_angle_deg)
    for door in doors:
        sign = 1.0 if door.name.endswith("_L") else -1.0
        door.rotation_euler = (sign * angle, 0.0, 0.0)
    mu.sync()


def build_doors(body: bpy.types.Object, materials,
                rig: cfg.RigConfig) -> list[bpy.types.Object]:
    doors = DoorBuilder(materials).split(body)
    pose_doors(doors, rig)
    return doors
