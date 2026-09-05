"""Dimensions and build/rig configuration.

Coordinate convention (see CLAUDE.md):
    metres, +Z up, the car faces **-X**, +Y is the car's left, ground plane at Z=0.
    World origin sits midway between the axles on the ground.

Published DMC-12 dimensions are the hard ground truth. Reference photographs are
shape confirmation, never measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

REQUIRED_BLENDER = (5, 2)

# --------------------------------------------------------------------------- car
LENGTH = 4.267
WIDTH = 1.988
HEIGHT = 1.140
WHEELBASE = 2.413

FRONT_AXLE_X = -WHEELBASE / 2
REAR_AXLE_X = WHEELBASE / 2

TRACK_FRONT = 1.588
TRACK_REAR = 1.605
HALF_TRACK_FRONT = TRACK_FRONT / 2
HALF_TRACK_REAR = TRACK_REAR / 2


@dataclass(frozen=True)
class WheelSpec:
    """A tyre size, resolved to metres."""

    section_mm: float           # tyre section width, e.g. 195
    aspect: float               # sidewall as a fraction of section, e.g. 0.60
    rim_in: float               # rim diameter in inches, e.g. 14

    @property
    def width(self) -> float:
        return self.section_mm / 1000.0

    @property
    def bead_radius(self) -> float:
        return self.rim_in * 0.0254 / 2.0

    @property
    def radius(self) -> float:
        return self.bead_radius + self.section_mm * self.aspect / 1000.0


WHEEL_FRONT = WheelSpec(195, 0.60, 14)     # 589.6 mm diameter
WHEEL_REAR = WheelSpec(235, 0.60, 15)      # 663.0 mm diameter

BODY_PANEL_THICKNESS = 0.024
PANEL_GAP = 0.006                          # shut line width


# ------------------------------------------------------------------------- rig
@dataclass
class RigConfig:
    """Poseable state. Nothing here may be baked into geometry."""

    door_angle_deg: float = 0.0            # gullwing opening, 0 = shut
    steer_deg: float = 0.0                 # front wheel steering
    wheel_spin_deg: float = 0.0            # rotation about the axle
    ride_height_offset: float = 0.0        # raises/lowers the body on its wheels

    @classmethod
    def doors_open(cls, angle: float = 52.0) -> "RigConfig":
        return cls(door_angle_deg=angle)


# ----------------------------------------------------------------------- build
@dataclass
class BuildConfig:
    """Everything the build itself can be told to do."""

    rig: RigConfig = field(default_factory=RigConfig)

    collection_name: str = "DeLorean"
    build_interior: bool = True
    build_scene: bool = True               # camera, lights, ground
    validate: bool = True

    # render. EEVEE is the fast default the visual tests run on; Cycles is for
    # finals, and handles glass, metal and contact shadows properly.
    engine: str = "eevee"                  # "eevee" | "cycles"
    resolution: tuple[int, int] = (1600, 900)
    samples: int = 64
    exposure: float = 0.0                  # calibrated against the studio world
    clay: bool = False                     # override all materials with flat grey

    # world. "procedural" is a neutral luminance gradient; "reference" reflects
    # one of the committed photographs, so the steel picks up the same
    # surroundings that lit the real car.
    environment: str = "reference"
    environment_reference: str = "front-quarter-left-gravel.jpg"
    environment_strength: float = 1.0
    environment_photo_mix: float = 0.62
    environment_rotation_deg: float = 0.0

    # flat colour the camera sees, without affecting reflections. None = show
    # the environment itself.
    backdrop: str | None = None

    seed: int = 0
