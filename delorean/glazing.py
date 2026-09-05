"""Glass, and the apertures it sits in.

The shell arrives closed over the greenhouse, so every window is cut before its
glass is placed. Windscreen and backlight are cut with vertical prisms — both
surfaces rise monotonically in Z across their footprint, so a plan-view outline
is enough. The quarter windows are cut across the car instead, because the sail
panel is close to vertical there.

Each pane is then built *from its own aperture outline*, sampled onto the body
surface and pushed in by `GLASS_INSET`. Building glass from the surface
parameter instead is what makes a windscreen spill out across the roof.
"""
from __future__ import annotations

import bpy

from . import mesh_utils as mu
from .body import flank_half_width, polygon_span, skin_z_at

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

#: Door daylight opening. Imported rather than restated: if the aperture and
#: its glass ever disagree, one of them is visibly wrong.
from .doors import WINDOW_OUTLINE as SIDE_OUTLINE  # noqa: E402

#: How far the glass sits below the surrounding steel.
GLASS_INSET = 0.017
#: How far the pane oversizes its aperture, so it tucks under the frame.
GLASS_OVERLAP = 0.008


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


# ---------------------------------------------------------------- pane makers
def _horizontal_pane(name: str, plan, nx: int = 14, ny: int = 10,
                     inset: float = GLASS_INSET,
                     grow: float = GLASS_OVERLAP) -> bpy.types.Object:
    """A pane lying on the roof surface, bounded by a plan-view outline."""
    xs = [p[0] for p in plan]
    x0, x1 = min(xs) - grow, max(xs) + grow

    verts, faces = [], []
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * (i / nx)
        span = polygon_span(plan, max(min(x, max(xs)), min(xs)))
        y_lo, y_hi = span if span else (0.0, 0.0)
        y_lo -= grow
        y_hi += grow
        for j in range(ny + 1):
            y = y_lo + (y_hi - y_lo) * (j / ny)
            verts.append((x, y, skin_z_at(x, y) - inset))
    for i in range(nx):
        for j in range(ny):
            a = i * (ny + 1) + j
            b = (i + 1) * (ny + 1) + j
            faces.append((a, a + 1, b + 1, b))
    return mu.obj_from_pydata(name, verts, faces)


def _flank_pane(name: str, outline, sign: int, nx: int = 14, nz: int = 6,
                inset: float = GLASS_INSET,
                grow: float = GLASS_OVERLAP) -> bpy.types.Object:
    """A pane lying on the flank, bounded by an outline in the XZ plane."""
    xs = [p[0] for p in outline]
    x0, x1 = min(xs) + 1e-4, max(xs) - 1e-4

    verts, faces = [], []
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * (i / nx)
        span = polygon_span(outline, x)
        z_lo, z_hi = span if span else (0.0, 0.0)
        z_lo -= grow
        z_hi += grow
        for j in range(nz + 1):
            z = z_lo + (z_hi - z_lo) * (j / nz)
            y = flank_half_width(x, z) - inset
            verts.append((x, sign * y, z))
    for i in range(nx):
        for j in range(nz):
            a = i * (nz + 1) + j
            b = (i + 1) * (nz + 1) + j
            faces.append((a, a + 1, b + 1, b))
    return mu.obj_from_pydata(name, verts, faces)


class GlazingBuilder:
    """Builds each pane on the body surface it belongs to."""

    def __init__(self, materials) -> None:
        self.materials = materials

    def _finish(self, ob: bpy.types.Object, material) -> bpy.types.Object:
        mu.set_material(ob, material)
        mu.shade_smooth(ob, 45)
        return ob

    def windscreen(self) -> bpy.types.Object:
        return self._finish(
            _horizontal_pane("Glass_Windscreen", WINDSCREEN_PLAN),
            self.materials["glass"])

    def backlight(self) -> bpy.types.Object:
        """Under the louvres, so it reads as near-black rather than clear."""
        return self._finish(
            _horizontal_pane("Glass_Backlight", BACKLIGHT_PLAN),
            self.materials["glass_dark"])

    def side(self, side: str, sign: int) -> bpy.types.Object:
        """Door glass. Parented to the door so it swings with it."""
        return self._finish(
            _flank_pane(f"Glass_Side_{side}", SIDE_OUTLINE, sign),
            self.materials["glass"])

    def quarter(self, side: str, sign: int) -> bpy.types.Object:
        return self._finish(
            _flank_pane(f"Glass_Quarter_{side}", QUARTER_OUTLINE, sign,
                        nx=6, nz=4),
            self.materials["glass_dark"])


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
