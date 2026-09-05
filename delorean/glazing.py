"""Glass, and the apertures it sits in.

The shell arrives closed over the greenhouse, so every window is cut before its
glass is placed. Windscreen and backlight are cut with vertical prisms — both
surfaces rise monotonically in Z across their footprint, so a plan-view outline
is enough. The quarter windows are cut across the car instead, because the sail
panel is close to vertical there.

Glass is built on the body's own upper-skin surface and pushed 17 mm into it,
which is what gives glazing its recess into the surrounding steel.
"""
from __future__ import annotations

import bpy

from . import mesh_utils as mu
from .body import skin_patch

#: Windscreen aperture, in plan. Sits inside the A-pillars, and stops short of
#: x = -0.20 so the header between it and the door cut stays 130 mm wide.
WINDSCREEN_PLAN = [
    (-0.995,  0.470), (-0.880,  0.575), (-0.470,  0.565), (-0.330,  0.455),
    (-0.330, -0.455), (-0.470, -0.565), (-0.880, -0.575), (-0.995, -0.470),
]

#: Backlight aperture, in plan. The louvres sit over this.
BACKLIGHT_PLAN = [
    ( 0.470,  0.520), ( 0.560,  0.545), ( 1.300,  0.470), ( 1.395,  0.420),
    ( 1.395, -0.420), ( 1.300, -0.470), ( 0.560, -0.545), ( 0.470, -0.520),
]

#: Quarter window in the sail panel, behind the door, in the XZ plane.
QUARTER_OUTLINE = [
    (0.470, 0.880), (0.700, 0.905), (0.640, 1.030), (0.482, 1.010),
]

GLASS_INSET = 0.017


def cut_apertures(body: bpy.types.Object) -> None:
    """Open the greenhouse. Must run before the glass is placed."""
    for name, plan in (("WindscreenCut", WINDSCREEN_PLAN),
                       ("BacklightCut", BACKLIGHT_PLAN)):
        cutter = mu.prism(name, plan, 0.62, 1.60, axis="Z")
        mu.boolean(body, cutter, 'DIFFERENCE')

    for sign in (1, -1):
        lo, hi = sorted((sign * 0.20, sign * 1.30))
        cutter = mu.prism("QuarterCut", QUARTER_OUTLINE, lo, hi, axis="Y")
        mu.boolean(body, cutter, 'DIFFERENCE')


class GlazingBuilder:
    """Builds each pane on the body surface it belongs to."""

    def __init__(self, materials) -> None:
        self.materials = materials

    def windscreen(self) -> bpy.types.Object:
        ob = skin_patch("Glass_Windscreen", -0.985, -0.340, -0.925, 0.925,
                        10, 16, offset=(0.0, 0.0, -GLASS_INSET))
        mu.set_material(ob, self.materials["glass"])
        mu.shade_smooth(ob, 45)
        return ob

    def backlight(self) -> bpy.types.Object:
        """Under the louvres, so it reads as near-black rather than clear."""
        ob = skin_patch("Glass_Backlight", 0.480, 1.385, -0.905, 0.905,
                        12, 16, offset=(0.0, 0.0, -GLASS_INSET))
        mu.set_material(ob, self.materials["glass_dark"])
        mu.shade_smooth(ob, 45)
        return ob

    def side(self, side: str, sign: int) -> bpy.types.Object:
        """Door glass. Parented to the door so it swings with it."""
        ob = skin_patch(f"Glass_Side_{side}", -0.880, 0.395,
                        sign * 1.02, sign * 1.92, 14, 6,
                        offset=(0.0, -sign * 0.013, 0.0))
        mu.set_material(ob, self.materials["glass"])
        mu.shade_smooth(ob, 45)
        return ob

    def quarter(self, side: str, sign: int) -> bpy.types.Object:
        ob = skin_patch(f"Glass_Quarter_{side}", 0.478, 0.700,
                        sign * 1.02, sign * 1.75, 4, 4,
                        offset=(0.0, -sign * 0.013, 0.0))
        mu.set_material(ob, self.materials["glass_dark"])
        mu.shade_smooth(ob, 45)
        return ob


def build_glazing(materials,
                  doors: list[bpy.types.Object] | None = None
                  ) -> list[bpy.types.Object]:
    builder = GlazingBuilder(materials)
    panes = [builder.windscreen(), builder.backlight()]

    by_side = {d.name[-1]: d for d in (doors or [])}
    for side, sign in (("L", 1), ("R", -1)):
        glass = builder.side(side, sign)
        door = by_side.get(side)
        if door is not None:
            glass.parent = door
            glass.matrix_parent_inverse = door.matrix_world.inverted()
        panes.append(glass)
        panes.append(builder.quarter(side, sign))

    mu.sync()
    return panes
