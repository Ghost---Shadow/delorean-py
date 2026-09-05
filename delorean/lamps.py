"""Head, tail, indicator and marker lamps set into the black fascia panels.

Reference: references/parts/lamps/nose-fascia.png (front assembly),
           references/parts/lamps/tail-panel-full.png (rear assembly).

Unlike the steel body, the DMC-12's lamps are simple rectangular add-on units
bolted into cut-outs in the black urethane fascia rather than shapes lofted
from the body surface. Every unit is still positioned from that surface,
though: `body.nose_x` / `body.tail_x` give the fascia's x at a given
half-width and height, and `body.flank_half_width` gives the same for the
side of the car, so a lamp's mounting face sits flush on the panel instead of
floating in space or burying itself in the steel.

Each lamp assembly is built as nested boxes of shrinking footprint standing
proud of one another toward the viewer -- lens in front of reflector in
front of bezel, headlamp-style, and lens cells proud of their black backing
plate on the tail clusters -- the same "stack simple primitives and let the
silhouette do the work" approach `wheels.WheelBuilder` uses for the hub and
cap. Every assembly is joined into a single multi-material object per the
`Lamp_` naming convention.
"""
from __future__ import annotations

import bpy

from . import mesh_utils as mu
from .body import flank_half_width, nose_x, tail_x

Vec3 = tuple[float, float, float]


class LampBuilder:
    """Builds one lamp assembly at a time; the module function mirrors L/R."""

    # ------------------------------------------------------ front fascia band
    #: the nose panel is flat between these heights (below it the bumper
    #: valance curves back and under; above it the hood line takes over) --
    #: this is where the headlamps and grille sit.
    FASCIA_Z0 = 0.375
    FASCIA_Z1 = 0.500

    GRILLE_HALF_W = 0.155        # grille slats span +/- this from centreline
    LAMP_GAP = 0.014             # gap between grille/lamp and lamp/lamp
    HEAD_W = 0.190
    HEAD_H = 0.130

    BEZEL_DEPTH = 0.030
    BEZEL_MARGIN = 0.016         # frame width left showing around the lens
    REFLECTOR_MARGIN = 0.008     # narrower inset -- the rim peeks past the lens
    LENS_PROUD = 0.012           # how far the lens stands out past the bezel
    LENS_DEPTH = 0.010
    REFLECTOR_DEPTH = 0.006

    #: horizontal-slat grille between the two headlamp pairs
    GRILLE_SLATS = 11
    GRILLE_DEPTH = 0.022
    GRILLE_SLAT_PROUD = 0.006
    GRILLE_DUTY = 0.55            # fraction of each slat's pitch that is fin

    #: amber indicators, low in the fascia below the headlamps
    INDICATOR_Y = 0.50
    INDICATOR_Z = 0.285
    INDICATOR_W = 0.160
    INDICATOR_H = 0.075
    INDICATOR_MARGIN = 0.010
    INDICATOR_DEPTH = 0.018
    INDICATOR_LENS_PROUD = 0.010
    INDICATOR_LENS_DEPTH = 0.008

    #: small amber marker on the front fender flank
    MARKER_F_X = -1.55
    MARKER_F_Z = 0.40
    MARKER_W = 0.050
    MARKER_H = 0.036
    MARKER_MARGIN = 0.008
    MARKER_DEPTH = 0.014
    MARKER_LENS_PROUD = 0.008
    MARKER_LENS_DEPTH = 0.006

    # -------------------------------------------------------- rear tail panel
    #: the full-width recessed black panel the taillamp clusters sit in
    PANEL_HALF_W = 0.80
    PANEL_Z0 = 0.360
    PANEL_Z1 = 0.620
    PANEL_RECESS = 0.035
    PANEL_THICK = 0.050

    #: four columns per cluster, outboard to inboard: amber, red, red, clear.
    #: each column is a 2-wide x 3-tall grid of small lenses.
    CLUSTER_Y0 = 0.300             # inboard edge of the cluster (nearest plate)
    CLUSTER_GROUP_W = 0.095        # width of one of the four columns
    CLUSTER_Z0 = 0.380
    CLUSTER_Z1 = 0.600
    CLUSTER_ROWS = 3
    CLUSTER_COLS = 2
    CELL_GAP = 0.006
    BACKING_RECESS = 0.015
    BACKING_THICK = 0.025
    LENS_RECESS = 0.002
    LENS_REAR_DEPTH = 0.012

    #: outboard to inboard column colour keys, matching the reference
    COLUMN_MATERIALS = ("lens_white", "lens_red", "lens_red", "lens_amber")

    #: small red marker on the rear fender flank
    MARKER_R_X = 1.90
    MARKER_R_Z = 0.35

    def __init__(self, materials) -> None:
        self.materials = materials

    # ------------------------------------------------------------- primitives
    def _slab(self, name: str, material: bpy.types.Material, face_x: float,
              depth: float, size_y: float, size_z: float,
              center_y: float, center_z: float,
              inward: float) -> bpy.types.Object:
        """A box whose `face_x` face is the visible one, growing `inward`.

        `inward` is +1 when moving away from the viewer means increasing x
        (front-of-car units, whose surface sits at very negative x) and -1
        when it means decreasing x (rear-of-car units).
        """
        cx = face_x + inward * depth / 2.0
        ob = mu.box(name, (depth, size_y, size_z), location=(cx, center_y, center_z))
        mu.set_material(ob, material)
        return ob

    def _side_slab(self, name: str, material: bpy.types.Material, face_y: float,
                   depth: float, size_x: float, size_z: float,
                   center_x: float, center_z: float,
                   inward: float) -> bpy.types.Object:
        """Like `_slab` but mounted on the flank, facing +-Y instead of +-X."""
        cy = face_y + inward * depth / 2.0
        ob = mu.box(name, (size_x, depth, size_z), location=(center_x, cy, center_z))
        mu.set_material(ob, material)
        return ob

    # ------------------------------------------------------------ headlamps
    def headlamp(self, tag: str, which: str, sign: float) -> bpy.types.Object:
        """One sealed-beam unit: black bezel, chrome reflector, glowing lens.

        `which` is "inner" (next to the grille) or "outer" (toward the
        fender corner) -- see references/parts/lamps/headlamp-*-pair.png.
        """
        if which == "inner":
            y0 = self.GRILLE_HALF_W + self.LAMP_GAP
        else:
            y0 = self.GRILLE_HALF_W + 2 * self.LAMP_GAP + self.HEAD_W
        y1 = y0 + self.HEAD_W
        cy = sign * (y0 + y1) / 2.0
        cz = (self.FASCIA_Z0 + self.FASCIA_Z1) / 2.0
        surf_x = nose_x((y0 + y1) / 2.0, cz)

        m = self.BEZEL_MARGIN
        rm = self.REFLECTOR_MARGIN
        bezel = self._slab(f"{tag}_{which}_bezel", self.materials["black"],
                           surf_x, self.BEZEL_DEPTH, self.HEAD_W, self.HEAD_H,
                           cy, cz, inward=1.0)
        lens_face = surf_x - self.LENS_PROUD
        lens = self._slab(f"{tag}_{which}_lens", self.materials["headlamp"],
                          lens_face, self.LENS_DEPTH,
                          self.HEAD_W - 2 * m, self.HEAD_H - 2 * m,
                          cy, cz, inward=1.0)
        reflector = self._slab(f"{tag}_{which}_reflector", self.materials["reflector"],
                               lens_face + self.LENS_DEPTH, self.REFLECTOR_DEPTH,
                               self.HEAD_W - 2 * rm, self.HEAD_H - 2 * rm,
                               cy, cz, inward=1.0)
        name = f"Lamp_Head_{tag}_{which.capitalize()}"
        return mu.join(name, [bezel, lens, reflector])

    # ------------------------------------------------------------- grille
    def grille(self) -> bpy.types.Object:
        """Horizontal-slat grille between the two headlamp pairs.

        Only the slats: the DMC badge that normally sits on top is a
        separate module's job.
        """
        cz = (self.FASCIA_Z0 + self.FASCIA_Z1) / 2.0
        surf_x = nose_x(self.GRILLE_HALF_W, cz)
        width = 2.0 * self.GRILLE_HALF_W
        height = self.FASCIA_Z1 - self.FASCIA_Z0

        backing = self._slab("grille_backing", self.materials["black"], surf_x,
                             self.GRILLE_DEPTH, width, height, 0.0, cz,
                             inward=1.0)
        parts = [backing]
        pitch = height / self.GRILLE_SLATS
        slat_h = pitch * self.GRILLE_DUTY
        slat_face = surf_x - self.GRILLE_SLAT_PROUD
        for i in range(self.GRILLE_SLATS):
            slat_z = self.FASCIA_Z0 + pitch * (i + 0.5)
            slat = self._slab(f"grille_slat_{i}", self.materials["black"],
                              slat_face, self.GRILLE_DEPTH * 0.6,
                              width * 0.96, slat_h, 0.0, slat_z, inward=1.0)
            parts.append(slat)
        return mu.join("Lamp_Grille", parts)

    # ---------------------------------------------------------- indicators
    def indicator(self, tag: str, sign: float) -> bpy.types.Object:
        """Amber turn signal, low in the fascia below the headlamps."""
        cy = sign * self.INDICATOR_Y
        cz = self.INDICATOR_Z
        surf_x = nose_x(self.INDICATOR_Y, cz)

        m = self.INDICATOR_MARGIN
        bezel = self._slab(f"{tag}_ind_bezel", self.materials["black"], surf_x,
                           self.INDICATOR_DEPTH, self.INDICATOR_W,
                           self.INDICATOR_H, cy, cz, inward=1.0)
        lens = self._slab(f"{tag}_ind_lens", self.materials["lens_amber"],
                          surf_x - self.INDICATOR_LENS_PROUD,
                          self.INDICATOR_LENS_DEPTH,
                          self.INDICATOR_W - 2 * m, self.INDICATOR_H - 2 * m,
                          cy, cz, inward=1.0)
        return mu.join(f"Lamp_Indicator_{tag}", [bezel, lens])

    # ------------------------------------------------------------- markers
    def front_marker(self, tag: str, sign: float) -> bpy.types.Object:
        """Small amber marker set into the front fender flank."""
        x, z = self.MARKER_F_X, self.MARKER_F_Z
        y_surf = sign * flank_half_width(x, z)
        inward = -sign

        m = self.MARKER_MARGIN
        bezel = self._side_slab(f"{tag}_fmark_bezel", self.materials["black"],
                                y_surf, self.MARKER_DEPTH, self.MARKER_W,
                                self.MARKER_H, x, z, inward)
        lens = self._side_slab(f"{tag}_fmark_lens", self.materials["lens_amber"],
                               y_surf + sign * self.MARKER_LENS_PROUD,
                               self.MARKER_LENS_DEPTH, self.MARKER_W - 2 * m,
                               self.MARKER_H - 2 * m, x, z, inward)
        return mu.join(f"Lamp_Marker_Front_{tag}", [bezel, lens])

    def rear_marker(self, tag: str, sign: float) -> bpy.types.Object:
        """Small red marker set into the rear fender flank."""
        x, z = self.MARKER_R_X, self.MARKER_R_Z
        y_surf = sign * flank_half_width(x, z)
        inward = -sign

        m = self.MARKER_MARGIN
        bezel = self._side_slab(f"{tag}_rmark_bezel", self.materials["black"],
                                y_surf, self.MARKER_DEPTH, self.MARKER_W,
                                self.MARKER_H, x, z, inward)
        lens = self._side_slab(f"{tag}_rmark_lens", self.materials["lens_red"],
                               y_surf + sign * self.MARKER_LENS_PROUD,
                               self.MARKER_LENS_DEPTH, self.MARKER_W - 2 * m,
                               self.MARKER_H - 2 * m, x, z, inward)
        return mu.join(f"Lamp_Marker_Rear_{tag}", [bezel, lens])

    # ---------------------------------------------------------- tail panel
    def tail_panel(self) -> bpy.types.Object:
        """The full-width recessed black panel both taillamp clusters sit in."""
        cz = (self.PANEL_Z0 + self.PANEL_Z1) / 2.0
        surf_x = tail_x(self.PANEL_HALF_W * 0.5, cz)
        width = 2.0 * self.PANEL_HALF_W
        height = self.PANEL_Z1 - self.PANEL_Z0
        ob = self._slab("Lamp_Tail_Panel", self.materials["black"],
                        surf_x - self.PANEL_RECESS, self.PANEL_THICK,
                        width, height, 0.0, cz, inward=-1.0)
        return ob

    # -------------------------------------------------------- tail clusters
    def tail_cluster(self, tag: str, sign: float) -> bpy.types.Object:
        """Four columns (amber, red, red, clear outboard to inboard).

        Each column is a 2x3 grid of small square lenses on a black backing,
        matching references/parts/lamps/taillamp-left.png /-right.png.
        """
        z0, z1 = self.CLUSTER_Z0, self.CLUSTER_Z1
        cz = (z0 + z1) / 2.0
        n_groups = len(self.COLUMN_MATERIALS)
        total_w = n_groups * self.CLUSTER_GROUP_W
        y_mid = self.CLUSTER_Y0 + total_w / 2.0
        surf_x = tail_x(y_mid, cz)

        backing_cy = sign * y_mid
        backing = self._slab(f"{tag}_tail_backing", self.materials["black"],
                             surf_x - self.BACKING_RECESS, self.BACKING_THICK,
                             total_w, z1 - z0, backing_cy, cz, inward=-1.0)
        parts = [backing]

        row_h = ((z1 - z0) - self.CELL_GAP * (self.CLUSTER_ROWS + 1)) / self.CLUSTER_ROWS
        col_w = (self.CLUSTER_GROUP_W - self.CELL_GAP * (self.CLUSTER_COLS + 1)) / self.CLUSTER_COLS
        lens_face = surf_x - self.LENS_RECESS

        # index 0 = innermost (nearest the plate); COLUMN_MATERIALS is given
        # outboard -> inboard, so read it back to front.
        inboard_to_outboard = list(reversed(self.COLUMN_MATERIALS))
        for g, mat_key in enumerate(inboard_to_outboard):
            g_y0 = self.CLUSTER_Y0 + g * self.CLUSTER_GROUP_W
            mat = self.materials[mat_key]
            for r in range(self.CLUSTER_ROWS):
                cell_z = z0 + self.CELL_GAP * (r + 1) + row_h * (r + 0.5)
                for c in range(self.CLUSTER_COLS):
                    cell_y = (g_y0 + self.CELL_GAP * (c + 1)
                             + col_w * (c + 0.5))
                    cell = self._slab(
                        f"{tag}_tail_g{g}_r{r}_c{c}", mat, lens_face,
                        self.LENS_REAR_DEPTH, col_w, row_h,
                        sign * cell_y, cell_z, inward=-1.0)
                    parts.append(cell)

        return mu.join(f"Lamp_Tail_{tag}", parts)


# --------------------------------------------------------------------- build
def build_lamps(materials) -> list[bpy.types.Object]:
    """Every lamp on the car: head, indicator and marker up front, taillamp
    cluster, panel and marker at the back.
    """
    builder = LampBuilder(materials)
    out: list[bpy.types.Object] = []

    out.append(builder.grille())
    out.append(builder.tail_panel())

    for sign, tag in ((1.0, "FL"), (-1.0, "FR")):
        out.append(builder.headlamp(tag, "inner", sign))
        out.append(builder.headlamp(tag, "outer", sign))
        out.append(builder.indicator(tag, sign))
        out.append(builder.front_marker(tag, sign))

    for sign, tag in ((1.0, "L"), (-1.0, "R")):
        out.append(builder.tail_cluster(tag, sign))
        out.append(builder.rear_marker(tag, sign))

    mu.sync()
    return out
