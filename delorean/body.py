"""The monocoque body shell.

Giugiaro's DMC-12 is a folded wedge with hard creases, not a blend of
primitives, so the shell is lofted from hand-authored cross-sections. Each
station carries eight points that run from the underbody centreline, out over
the sill, up the flank past the swage crease, across the shoulder, up the
tumblehome and over the roof back to the centreline.

Only the left half is authored; the right half is mirrored, which guarantees
symmetry by construction.
"""
from __future__ import annotations

from dataclasses import dataclass

import bpy

from . import config as cfg
from . import mesh_utils as mu

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Station:
    """One cross-section of the body, at longitudinal position `x`."""

    x: float
    z_bot: float        # underbody height
    y_floor: float      # half-width of the flat underbody
    y_max: float        # widest half-width, at the swage crease
    z_rock: float       # rocker / bottom of the visible flank
    z_belt: float       # top of the flank
    y_glass: float      # half-width at the base of the greenhouse
    z_shoulder: float   # height at that point
    y_roof: float       # half-width of the roof / drip rail
    z_roof: float       # roof height

    #: fraction of the way up the flank at which the swage crease sits
    SWAGE_T = 0.46
    #: the flank pinches in very slightly above and below the crease
    ROCKER_TAPER = 0.958
    BELT_TAPER = 0.988
    #: the roof crowns a touch at the centreline
    ROOF_CROWN = 0.008

    def ring(self) -> list[Vec3]:
        z_swage = self.z_rock + self.SWAGE_T * (self.z_belt - self.z_rock)
        return [
            (self.x, 0.0,                          self.z_bot),
            (self.x, self.y_floor,                 self.z_bot),
            (self.x, self.y_max * self.ROCKER_TAPER, self.z_rock),
            (self.x, self.y_max,                   z_swage),
            (self.x, self.y_max * self.BELT_TAPER, self.z_belt),
            (self.x, self.y_glass,                 self.z_shoulder),
            (self.x, self.y_roof,                  self.z_roof),
            (self.x, 0.0,                          self.z_roof + self.ROOF_CROWN),
        ]


# Nose (-X) to tail (+X). The cowl at x=-1.000 is where the top skin stops being
# the bonnet and becomes the windscreen; the roof runs -0.170..+0.340; behind
# that the long, shallow fastback falls away to the tail.
STATIONS: tuple[Station, ...] = (
    Station(-2.134, 0.255, 0.187, 0.598, 0.360, 0.500, 0.402, 0.520, 0.201, 0.528),
    Station(-2.108, 0.220, 0.262, 0.710, 0.322, 0.540, 0.476, 0.556, 0.238, 0.563),
    Station(-2.062, 0.186, 0.318, 0.811, 0.292, 0.574, 0.537, 0.586, 0.269, 0.592),
    Station(-1.980, 0.152, 0.383, 0.872, 0.268, 0.606, 0.575, 0.617, 0.290, 0.622),
    Station(-1.860, 0.138, 0.411, 0.904, 0.256, 0.633, 0.596, 0.643, 0.299, 0.648),
    Station(-1.650, 0.132, 0.430, 0.921, 0.250, 0.658, 0.613, 0.668, 0.308, 0.673),
    Station(-1.400, 0.129, 0.439, 0.927, 0.246, 0.678, 0.617, 0.688, 0.308, 0.693),
    Station(-1.150, 0.128, 0.439, 0.928, 0.244, 0.698, 0.617, 0.708, 0.308, 0.713),
    Station(-1.000, 0.128, 0.439, 0.928, 0.243, 0.715, 0.747, 0.742, 0.673, 0.752),
    Station(-0.900, 0.128, 0.439, 0.928, 0.243, 0.735, 0.775, 0.775, 0.682, 0.792),
    Station(-0.600, 0.128, 0.439, 0.928, 0.243, 0.775, 0.794, 0.828, 0.654, 0.945),
    Station(-0.340, 0.128, 0.439, 0.928, 0.243, 0.795, 0.794, 0.862, 0.612, 1.070),
    Station(-0.170, 0.128, 0.439, 0.928, 0.243, 0.800, 0.794, 0.872, 0.584, 1.130),
    Station(0.100, 0.128, 0.439, 0.928, 0.243, 0.805, 0.794, 0.878, 0.577, 1.142),
    Station(0.340, 0.130, 0.439, 0.928, 0.244, 0.808, 0.789, 0.880, 0.560, 1.136),
    Station(0.620, 0.134, 0.439, 0.928, 0.246, 0.811, 0.778, 0.882, 0.537, 1.062),
    Station(1.000, 0.140, 0.439, 0.928, 0.249, 0.812, 0.761, 0.881, 0.509, 0.968),
    Station(1.400, 0.150, 0.430, 0.927, 0.254, 0.811, 0.736, 0.876, 0.478, 0.892),
    Station(1.750, 0.163, 0.411, 0.917, 0.266, 0.805, 0.682, 0.861, 0.420, 0.866),
    Station(2.030, 0.203, 0.355, 0.895, 0.298, 0.791, 0.598, 0.838, 0.332, 0.842),
    Station(2.134, 0.263, 0.262, 0.829, 0.358, 0.762, 0.495, 0.782, 0.266, 0.788),
)

_FIELDS = ("x", "z_bot", "y_floor", "y_max", "z_rock", "z_belt",
           "y_glass", "z_shoulder", "y_roof", "z_roof")


def station_at(x: float) -> Station:
    """Linearly interpolate a cross-section at arbitrary x."""
    xs = [s.x for s in STATIONS]
    x = max(xs[0], min(xs[-1], x))
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            a, b = STATIONS[i], STATIONS[i + 1]
            return Station(*[getattr(a, f) + (getattr(b, f) - getattr(a, f)) * t
                             for f in _FIELDS])
    return STATIONS[-1]


# ------------------------------------------------------------ surface queries
def skin_point(x: float, u: float) -> Vec3:
    """A point on the upper skin.

    `u` runs 0 at the roof centreline, +-1 at the roof edge / drip rail, and
    +-2 at the bottom of the side glass. Sign selects the side.
    """
    s = station_at(x)
    centre = (0.0, s.z_roof + Station.ROOF_CROWN)
    edge = (s.y_roof, s.z_roof)
    shoulder = (s.y_glass, s.z_shoulder)

    a = abs(u)
    sign = 1.0 if u >= 0 else -1.0
    if a <= 1.0:
        y = centre[0] + (edge[0] - centre[0]) * a
        z = centre[1] + (edge[1] - centre[1]) * a
    else:
        t = min(a - 1.0, 1.0)
        y = edge[0] + (shoulder[0] - edge[0]) * t
        z = edge[1] + (shoulder[1] - edge[1]) * t
    return (x, sign * y, z)


def skin_patch(name: str, x0: float, x1: float, u0: float, u1: float,
               nx: int, nu: int,
               offset: Vec3 = (0.0, 0.0, 0.0)) -> bpy.types.Object:
    """A quad grid lying on the upper skin, optionally pushed off it."""
    verts: list[Vec3] = []
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * (i / nx)
        for j in range(nu + 1):
            u = u0 + (u1 - u0) * (j / nu)
            p = skin_point(x, u)
            verts.append((p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]))

    faces = []
    for i in range(nx):
        for j in range(nu):
            a = i * (nu + 1) + j
            b = (i + 1) * (nu + 1) + j
            faces.append((a, a + 1, b + 1, b))
    return mu.obj_from_pydata(name, verts, faces)


def skin_z_at(x: float, y: float) -> float:
    """Height of the upper skin directly above (x, y).

    The inverse of `skin_point` in the plane: glazing has to be built from its
    aperture outline in plan, not from the surface parameter, or the pane
    spills out over the roof.
    """
    s = station_at(x)
    a = abs(y)
    crown = s.z_roof + Station.ROOF_CROWN
    if s.y_roof > 1e-6 and a <= s.y_roof:
        return crown + (s.z_roof - crown) * (a / s.y_roof)
    span = s.y_glass - s.y_roof
    if abs(span) < 1e-6:
        return s.z_roof
    t = max(0.0, min(1.0, (a - s.y_roof) / span))
    return s.z_roof + (s.z_shoulder - s.z_roof) * t


def polygon_span(poly, u: float) -> tuple[float, float] | None:
    """Range of the second coordinate inside `poly` at first coordinate `u`."""
    hits = []
    n = len(poly)
    for i in range(n):
        (a0, b0), (a1, b1) = poly[i], poly[(i + 1) % n]
        if (a0 - u) * (a1 - u) > 0 or abs(a1 - a0) < 1e-12:
            continue
        t = (u - a0) / (a1 - a0)
        hits.append(b0 + (b1 - b0) * t)
    if len(hits) < 2:
        return None
    return min(hits), max(hits)


def flank_half_width(x: float, z: float) -> float:
    """Half-width of the outer skin at height z, at station x. 0 if outside."""
    ring = station_at(x).ring()
    best = 0.0
    for a, b in zip(ring, ring[1:]):
        z0, z1 = a[2], b[2]
        if (z0 - z) * (z1 - z) <= 0.0 and abs(z1 - z0) > 1e-9:
            t = (z - z0) / (z1 - z0)
            best = max(best, a[1] + (b[1] - a[1]) * t)
    return best


def _sweep_x(y: float, z: float, x0: float, x1: float, steps: int = 200) -> float:
    for i in range(steps + 1):
        x = x0 + (x1 - x0) * i / steps
        if flank_half_width(x, z) >= y:
            return x
    return x1


def nose_x(y: float, z: float) -> float:
    """Longitudinal position of the front skin at a given height and half-width."""
    return _sweep_x(y, z, -2.140, -1.500)


def tail_x(y: float, z: float) -> float:
    """Longitudinal position of the rear skin at a given height and half-width."""
    return _sweep_x(y, z, 2.140, 1.500)


# ------------------------------------------------------------- material zoning
# The DMC-12 wears bare steel above a black urethane band: rocker mouldings the
# length of the car, rising into the bumpers at each end. The rise starts well
# back from the extremities, so the transition reads as a moulding wrapping the
# corners rather than a black nose and tail.
_FRONT_BUMPER_X = -1.82
_REAR_BUMPER_X = 1.86
_ROCKER_TOP = 0.325
#: how high the band climbs at each extremity
_FRONT_BUMPER_TOP = 0.485
_REAR_BUMPER_TOP = 0.560


def is_black_trim(x: float, y: float, z: float) -> bool:
    """True where the shell is black urethane rather than bare steel."""
    if x < _FRONT_BUMPER_X:
        t = min(1.0, (_FRONT_BUMPER_X - x) / 0.30)
        return z < _ROCKER_TOP + t * (_FRONT_BUMPER_TOP - _ROCKER_TOP)
    if x > _REAR_BUMPER_X:
        t = min(1.0, (x - _REAR_BUMPER_X) / 0.26)
        return z < _ROCKER_TOP + t * (_REAR_BUMPER_TOP - _ROCKER_TOP)
    return z < _ROCKER_TOP


def zone_body_materials(ob: bpy.types.Object, materials) -> None:
    """Steel everywhere except the bumpers and rocker mouldings."""
    mu.assign_materials(
        ob, [materials["steel"], materials["black"]],
        lambda x, y, z: 1 if is_black_trim(x, y, z) else 0)


# ---------------------------------------------------------------------- build
class BodyBuilder:
    """Lofts the shell, cuts the wheel arches and gives the panels thickness."""

    #: wheel arch openings: (axle x, centre height, radius)
    ARCH_FRONT = (cfg.FRONT_AXLE_X, 0.300, 0.360)
    ARCH_REAR = (cfg.REAR_AXLE_X, 0.330, 0.398)
    ARCH_INBOARD = 0.500        # inner wall of the wheel well
    ARCH_OUTBOARD = 1.180

    def __init__(self, materials) -> None:
        self.materials = materials

    def build(self) -> bpy.types.Object:
        body = mu.loft("Body", [s.ring() for s in STATIONS])
        mu.mirror_y(body)
        self._require_solid(body, "after mirror")

        self._cut_arches(body)
        self._require_solid(body, "after wheel arches")

        mu.solidify(body, cfg.BODY_PANEL_THICKNESS, offset=-1.0, even=False)
        self._require_solid(body, "after solidify")
        return body

    @staticmethod
    def _require_solid(ob: bpy.types.Object, stage: str) -> None:
        ok, detail = mu.is_solid(ob)
        if not ok:
            raise RuntimeError(
                f"body shell is not a valid solid {stage}: {detail}. "
                f"Every later boolean depends on this, so failing here beats "
                f"producing a car with one side missing.")

    def _cut_arches(self, body: bpy.types.Object) -> None:
        depth = self.ARCH_OUTBOARD - self.ARCH_INBOARD
        centre = (self.ARCH_INBOARD + self.ARCH_OUTBOARD) / 2.0
        for axle_x, cz, radius in (self.ARCH_FRONT, self.ARCH_REAR):
            for sign in (1, -1):
                cutter = mu.cylinder("ArchCut", radius, depth,
                                     location=(axle_x, sign * centre, cz),
                                     axis="Y", segments=56)
                mu.boolean(body, cutter, 'DIFFERENCE')
