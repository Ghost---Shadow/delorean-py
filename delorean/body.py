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
    Station(-2.134, 0.255, 0.20, 0.640, 0.360, 0.500, 0.430, 0.520, 0.215, 0.528),
    Station(-2.108, 0.220, 0.28, 0.760, 0.322, 0.540, 0.510, 0.556, 0.255, 0.563),
    Station(-2.062, 0.186, 0.34, 0.868, 0.292, 0.574, 0.575, 0.586, 0.288, 0.592),
    Station(-1.980, 0.152, 0.41, 0.934, 0.268, 0.606, 0.616, 0.617, 0.310, 0.622),
    Station(-1.860, 0.138, 0.44, 0.968, 0.256, 0.633, 0.638, 0.643, 0.320, 0.648),
    Station(-1.650, 0.132, 0.46, 0.986, 0.250, 0.658, 0.656, 0.668, 0.330, 0.673),
    Station(-1.400, 0.129, 0.47, 0.992, 0.246, 0.678, 0.660, 0.688, 0.330, 0.693),
    Station(-1.150, 0.128, 0.47, 0.994, 0.244, 0.698, 0.660, 0.708, 0.330, 0.713),
    Station(-1.000, 0.128, 0.47, 0.994, 0.243, 0.715, 0.800, 0.742, 0.720, 0.752),
    Station(-0.900, 0.128, 0.47, 0.994, 0.243, 0.735, 0.830, 0.775, 0.730, 0.792),
    Station(-0.600, 0.128, 0.47, 0.994, 0.243, 0.775, 0.850, 0.828, 0.700, 0.945),
    Station(-0.340, 0.128, 0.47, 0.994, 0.243, 0.795, 0.850, 0.862, 0.655, 1.070),
    Station(-0.170, 0.128, 0.47, 0.994, 0.243, 0.800, 0.850, 0.872, 0.625, 1.130),
    Station( 0.100, 0.128, 0.47, 0.994, 0.243, 0.805, 0.850, 0.878, 0.618, 1.142),
    Station( 0.340, 0.130, 0.47, 0.994, 0.244, 0.808, 0.845, 0.880, 0.600, 1.136),
    Station( 0.620, 0.134, 0.47, 0.994, 0.246, 0.811, 0.833, 0.882, 0.575, 1.062),
    Station( 1.000, 0.140, 0.47, 0.994, 0.249, 0.812, 0.815, 0.881, 0.545, 0.968),
    Station( 1.400, 0.150, 0.46, 0.992, 0.254, 0.811, 0.788, 0.876, 0.512, 0.892),
    Station( 1.750, 0.163, 0.44, 0.982, 0.266, 0.805, 0.730, 0.861, 0.450, 0.866),
    Station( 2.030, 0.203, 0.38, 0.958, 0.298, 0.791, 0.640, 0.838, 0.355, 0.842),
    Station( 2.134, 0.263, 0.28, 0.888, 0.358, 0.762, 0.530, 0.782, 0.285, 0.788),
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
#: the front bumper's top edge climbs as it runs forward
_FRONT_BUMPER_X = -1.66
_REAR_BUMPER_X = 1.64
_ROCKER_TOP = 0.335


def is_black_trim(x: float, y: float, z: float) -> bool:
    """True where the shell is black urethane rather than bare steel."""
    if x < _FRONT_BUMPER_X:
        top = min(0.52, _ROCKER_TOP + (_FRONT_BUMPER_X - x) / 0.40 * 0.185)
        return z < top
    if x > _REAR_BUMPER_X:
        top = min(0.655, _ROCKER_TOP + (x - _REAR_BUMPER_X) / 0.40 * 0.330)
        return z < top
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
