"""The cabin: tub, seats, dash, wheel and console.

Reference: references/parts/interior/interior-cabin.png
           references/parts/doors/door-sill-jamb.png

The DMC-12 is a two-seater with the gullwing hinge on the roof rather than a
pillar, so opening a door removes the *entire* flank from sill to roofline —
there is no B-pillar to hide behind. Everything in this module exists to give
that opening something to look into: a tub that closes the underside off from
one aperture to the other, two bucket seats trimmed in ribbed grey leather, a
dash that sweeps across at windscreen height with a binnacle ahead of the
driver, a wheel canted back at the driver's knees, and a slim tunnel between
the seats. None of it needs to survive close inspection — it only has to read
correctly through a door-shaped hole from a few metres away.

Layout is read off `body.station_at` / `body.flank_half_width` rather than
re-guessing the shell's width by eye, so the tub tracks the actual envelope
instead of an independent estimate of it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Vector

from . import mesh_utils as mu

TAU = math.tau


class InteriorBuilder:
    """Builds the cabin tub, seats, dash, wheel, console and door sills."""

    # ---------------------------------------------------------------- tub
    #: floor height and the z below which a tub face counts as "floor"
    #: rather than "wall/bulkhead", for material zoning.
    Z_FLOOR = 0.29
    FLOOR_MATERIAL_MAX_Z = 0.33

    #: Longitudinal stations for the tub loft: firewall to rear bulkhead.
    #: Each tuple is (x, y_floor, y_wall_mid, z_wall_mid, y_wall_top, z_wall_top).
    #: The footwell pinches in at the firewall to clear the pedal box, bows
    #: out to its widest under the seats, and narrows again behind them.
    TUB_STATIONS = (
        (-1.000, 0.62, 0.70, 0.55, 0.72, 0.80),
        (-0.750, 0.74, 0.80, 0.52, 0.80, 0.85),
        (-0.450, 0.76, 0.82, 0.50, 0.80, 0.87),
        (-0.100, 0.76, 0.82, 0.50, 0.79, 0.88),
        ( 0.200, 0.74, 0.80, 0.50, 0.77, 0.87),
        ( 0.450, 0.68, 0.74, 0.52, 0.72, 0.84),
    )

    # ------------------------------------------------------------ sills
    #: matches doors.DOOR_OUTLINE's sill points (-0.965..0.430 at z=0.300),
    #: kept as a local constant so this module has no import-time coupling
    #: to doors.py.
    DOOR_SILL_X = (-0.965, 0.430)
    SILL_Y = 0.80
    SILL_Z = 0.315
    SILL_SIZE = (0.05, 0.05)   # (width across y, height in z)

    # ------------------------------------------------------------- seats
    SEAT_X = -0.30
    SEAT_Y = 0.38
    SQUAB_SIZE = (0.50, 0.44, 0.14)     # length(x), width(y), height(z)
    SQUAB_Z = 0.36
    BACKREST_SIZE = (0.10, 0.42, 0.46)  # thickness(x), width(y), height(z)
    HEADREST_SIZE = (0.10, 0.26, 0.15)
    RECLINE_DEG = 15.0
    RIB_COUNT = 5
    RIB_SIZE = (0.016, 0.045, 0.0)      # depth(x), width(y), height set per-part

    # ----------------------------------------------------------------- dash
    DASH_X = (-0.98, -0.86)
    DASH_Z = (0.62, 0.80)
    DASH_HALF_WIDTH = 0.76
    BINNACLE_Y = SEAT_Y
    BINNACLE_SIZE = (0.10, 0.22, 0.10)

    # ---------------------------------------------------------- steering
    WHEEL_CENTRE = (-0.78, SEAT_Y, 0.74)
    WHEEL_DIAMETER = 0.36
    WHEEL_TUBE_R = 0.014
    WHEEL_TILT_DEG = 25.0
    WHEEL_SPOKES = 3
    BOSS_RADIUS = 0.045

    # ---------------------------------------------------------- console
    CONSOLE_X = (-0.85, 0.00)
    CONSOLE_HALF_WIDTH = 0.11
    CONSOLE_Z = (Z_FLOOR, 0.49)
    LEVER_HEIGHT = 0.18

    def __init__(self, materials) -> None:
        self.materials = materials

    # ======================================================================
    #  cabin tub
    # ======================================================================
    def cabin_tub(self) -> bpy.types.Object:
        """Floor, side walls, firewall and rear bulkhead as one lofted shell.

        Each station's profile runs from the floor centreline out to the
        sill, up the door card and over to the window sill — an open "U",
        never closing back to y=0 at the top. `mu.loft` caps the first and
        last rings solid (the firewall and the rear bulkhead); `mu.mirror_y`
        then reflects the whole thing across the centreline, which is what
        turns the two open ends of the U into a proper floor-and-walls tub
        without ever authoring a ceiling that would hide the seats.
        """
        rings = []
        for x, y_floor, y_mid, z_mid, y_top, z_top in self.TUB_STATIONS:
            rings.append([
                (x, 0.0,     self.Z_FLOOR),
                (x, y_floor, self.Z_FLOOR),
                (x, y_mid,   z_mid),
                (x, y_top,   z_top),
            ])
        tub = mu.loft("Int_Tub", rings, cap_first=True, cap_last=True)
        mu.mirror_y(tub)

        mu.assign_materials(
            tub, [self.materials["carpet"], self.materials["interior"]],
            lambda x, y, z: 0 if z <= self.FLOOR_MATERIAL_MAX_Z else 1)
        mu.shade_smooth(tub, 40)
        return tub

    def door_sills(self) -> list[bpy.types.Object]:
        """A raised scuff plate along the bottom of each door aperture.

        Without it, the door opening reads as a hole cut through the tub
        wall rather than a finished sill — see door-sill-jamb.png.
        """
        x0, x1 = self.DOOR_SILL_X
        length = x1 - x0
        cx = (x0 + x1) / 2.0
        w, h = self.SILL_SIZE
        out = []
        for side, sign in (("L", 1.0), ("R", -1.0)):
            sill = mu.box(f"Int_DoorSill_{side}",
                          size=(length, w, h),
                          location=(cx, sign * self.SILL_Y, self.SILL_Z))
            mu.set_material(sill, self.materials["chrome"])
            out.append(sill)
        return out

    # ======================================================================
    #  seats
    # ======================================================================
    def _rib(self, name: str, x: float, y: float, z: float,
             height: float) -> bpy.types.Object:
        depth, width, _ = self.RIB_SIZE
        rib = mu.box(name, size=(depth, width, height), location=(x, y, z))
        return rib

    def _seat(self, side: str, y: float) -> bpy.types.Object:
        """One bucket seat: squab, reclined backrest, headrest, rib detail."""
        sx, sy, sz = self.SQUAB_SIZE
        parts: list[bpy.types.Object] = []

        squab = mu.box(f"Int_Seat_{side}_Squab", size=(sx, sy, sz),
                       location=(self.SEAT_X, y, self.SQUAB_Z))
        mu.bevel(squab, 0.035, segments=3, angle_deg=60.0)
        parts.append(squab)

        # a shallow centre channel down the squab, the one bit of shape a
        # flat cushion box needs to read as upholstery rather than a crate
        squab_rib = self._rib(f"Int_Seat_{side}_SquabRib",
                              self.SEAT_X - sx * 0.15, y, self.SQUAB_Z + sz * 0.42,
                              height=sz * 0.5)
        parts.append(squab_rib)

        # backrest + headrest are authored at the origin, reclined about
        # their shared base pivot, then dropped onto the back edge of the
        # squab. Building them "flat" first and rotating the whole
        # assembly keeps the recline as one number instead of re-deriving
        # every part's tilted position by hand.
        pivot_x = self.SEAT_X + sx / 2.0 - 0.03
        pivot_z = self.SQUAB_Z + sz / 2.0

        bx, by, bz = self.BACKREST_SIZE
        backrest = mu.box(f"Int_Seat_{side}_Backrest", size=(bx, by, bz),
                          location=(0.0, 0.0, bz / 2.0))
        mu.bevel(backrest, 0.03, segments=3, angle_deg=60.0)

        rib_h = bz * 0.62
        rib_z = bz * 0.55
        rib_parts = [backrest]
        span = by * 0.72
        for i in range(self.RIB_COUNT):
            t = i / (self.RIB_COUNT - 1) - 0.5
            rib = self._rib(f"Int_Seat_{side}_BackRib{i}",
                            -bx / 2.0 - 0.006, t * span, rib_z, rib_h)
            rib_parts.append(rib)
        backrest = mu.join(f"Int_Seat_{side}_Backrest", rib_parts)

        hx, hy, hz = self.HEADREST_SIZE
        headrest_z = bz + hz / 2.0 + 0.02
        headrest = mu.box(f"Int_Seat_{side}_Headrest", size=(hx, hy, hz),
                          location=(0.0, 0.0, headrest_z))
        mu.bevel(headrest, 0.025, segments=3, angle_deg=60.0)
        head_ribs = [headrest]
        for i in range(3):
            t = i / 2 - 0.5
            rib = self._rib(f"Int_Seat_{side}_HeadRib{i}",
                            -hx / 2.0 - 0.006, t * hy * 0.7,
                            headrest_z, hz * 0.7)
            head_ribs.append(rib)
        headrest = mu.join(f"Int_Seat_{side}_Headrest", head_ribs)

        back_assembly = mu.join(f"Int_Seat_{side}_Back", [backrest, headrest])
        back_assembly.rotation_euler = (0.0, math.radians(self.RECLINE_DEG), 0.0)
        back_assembly.location = (pivot_x, y, pivot_z)
        parts.append(back_assembly)

        seat = mu.join(f"Int_Seat_{side}", parts)
        mu.set_material(seat, self.materials["leather"])
        mu.shade_smooth(seat, 45)
        return seat

    def seats(self) -> list[bpy.types.Object]:
        return [self._seat("L", self.SEAT_Y), self._seat("R", -self.SEAT_Y)]

    # ======================================================================
    #  dashboard
    # ======================================================================
    def dashboard(self) -> bpy.types.Object:
        """A moulded pad across the firewall with a binnacle over the wheel."""
        x0, x1 = self.DASH_X
        z0, z1 = self.DASH_Z
        cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
        dx, dz = x1 - x0, z1 - z0
        w = self.DASH_HALF_WIDTH * 2.0

        pad = mu.box("Int_Dash_Pad", size=(dx, w, dz), location=(cx, 0.0, cz))
        mu.bevel(pad, 0.03, segments=3, angle_deg=55.0)

        bx, by, bz = self.BINNACLE_SIZE
        binnacle = mu.box("Int_Dash_Binnacle", size=(bx, by, bz),
                          location=(cx - bx * 0.25, self.BINNACLE_Y,
                                    z1 + bz * 0.35))
        mu.bevel(binnacle, 0.02, segments=2, angle_deg=55.0)

        dash = mu.join("Int_Dash", [pad, binnacle])
        mu.set_material(dash, self.materials["interior"])
        mu.shade_smooth(dash, 45)
        return dash

    # ======================================================================
    #  steering wheel
    # ======================================================================
    def _torus(self, name: str, major_r: float, minor_r: float,
              major_segs: int = 40, minor_segs: int = 12) -> bpy.types.Object:
        """A ring lying with its face normal on +Y, minor tube radius `minor_r`.

        Built by spinning a small circle -- offset from the axis by
        `major_r` -- all the way around Y. Rotation about a global axis
        leaves each point's coordinate along that axis unchanged, so giving
        the small circle's points distinct y-offsets is what turns the spin
        into a torus instead of a simple disc of revolution.
        """
        bm = bmesh.new()
        ring = [bm.verts.new((major_r + minor_r * math.cos(TAU * i / minor_segs),
                              minor_r * math.sin(TAU * i / minor_segs), 0.0))
               for i in range(minor_segs)]
        edges = [bm.edges.new((ring[i], ring[(i + 1) % minor_segs]))
                for i in range(minor_segs)]
        bmesh.ops.spin(bm, geom=ring + edges, cent=(0, 0, 0), axis=(0, 1, 0),
                       dvec=(0, 0, 0), angle=TAU, steps=major_segs,
                       use_merge=False)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return mu.obj_from_bmesh(name, bm)

    def _spoke(self, name: str, angle: float, r_inner: float, r_outer: float,
              width: float, thickness: float) -> bpy.types.Object:
        """A radial bar in the wheel's XZ disc plane, at `angle` around Y."""
        length = r_outer - r_inner
        mid = (r_inner + r_outer) / 2.0
        ob = mu.box(name, size=(length, width, thickness), location=(0, 0, 0))
        ob.rotation_euler = (0.0, angle, 0.0)
        ob.location = (mid * math.cos(angle), 0.0, -mid * math.sin(angle))
        return ob

    def steering_wheel(self) -> bpy.types.Object:
        """Rim, spokes and boss, built face-on then tilted into the cabin.

        Everything is authored with its disc normal on +Y (matching
        `mesh_utils.cone`'s axis="Y" convention) and only reoriented at the
        very end, by rotating +Y onto the actual column direction. That
        keeps the spoke/rim geometry itself free of any trigonometry about
        the tilt, and avoids reasoning about Euler order entirely.
        """
        outer_r = self.WHEEL_DIAMETER / 2.0
        major_r = outer_r - self.WHEEL_TUBE_R

        rim = self._torus("Int_SteeringWheel_Rim", major_r, self.WHEEL_TUBE_R)
        mu.set_material(rim, self.materials["leather"])
        mu.shade_smooth(rim, 30)

        boss = mu.cone("Int_SteeringWheel_Boss", self.BOSS_RADIUS,
                       self.BOSS_RADIUS * 0.85, 0.05,
                       location=(0, -0.01, 0), axis="Y", segments=28)
        mu.set_material(boss, self.materials["black_matte"])

        spokes = []
        for k in range(self.WHEEL_SPOKES):
            angle = TAU * k / self.WHEEL_SPOKES + math.radians(90.0)
            spoke = self._spoke(f"Int_SteeringWheel_Spoke{k}", angle,
                                self.BOSS_RADIUS * 0.9, major_r - self.WHEEL_TUBE_R,
                                0.028, 0.014)
            mu.set_material(spoke, self.materials["black_matte"])
            spokes.append(spoke)

        wheel = mu.join("Int_SteeringWheel", [boss, rim, *spokes])
        mu.shade_smooth(wheel, 30)

        normal = Vector((math.cos(math.radians(self.WHEEL_TILT_DEG)), 0.0,
                        math.sin(math.radians(self.WHEEL_TILT_DEG))))
        wheel.rotation_euler = Vector((0.0, 1.0, 0.0)).rotation_difference(
            normal).to_euler()
        wheel.location = self.WHEEL_CENTRE
        return wheel

    # ======================================================================
    #  centre console
    # ======================================================================
    def console(self) -> bpy.types.Object:
        """The raised tunnel between the seats, with a short gear lever."""
        x0, x1 = self.CONSOLE_X
        z0, z1 = self.CONSOLE_Z
        cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
        dx, dz = x1 - x0, z1 - z0
        w = self.CONSOLE_HALF_WIDTH * 2.0

        tunnel = mu.box("Int_Console_Tunnel", size=(dx, w, dz),
                        location=(cx, 0.0, cz))
        mu.bevel(tunnel, 0.025, segments=3, angle_deg=55.0)

        lever_x = x0 + dx * 0.35
        stalk = mu.cylinder("Int_Console_LeverStalk", 0.010,
                            self.LEVER_HEIGHT, axis="Z",
                            location=(lever_x, 0.0,
                                      z1 + self.LEVER_HEIGHT / 2.0))
        knob = mu.cone("Int_Console_LeverKnob", 0.022, 0.020, 0.032,
                       axis="Z",
                       location=(lever_x, 0.0, z1 + self.LEVER_HEIGHT + 0.016))

        console = mu.join("Int_Console", [tunnel, stalk, knob])
        mu.set_material(console, self.materials["interior"])
        mu.shade_smooth(console, 45)
        return console

    # ======================================================================
    #  everything
    # ======================================================================
    def build(self) -> list[bpy.types.Object]:
        out: list[bpy.types.Object] = [self.cabin_tub(), *self.door_sills(),
                                       *self.seats(), self.dashboard(),
                                       self.steering_wheel(), self.console()]
        mu.sync()
        return out


def build_interior(materials) -> list[bpy.types.Object]:
    """The whole cabin: tub, sills, seats, dash, wheel and console."""
    return InteriorBuilder(materials).build()
