"""Visual unit tests for delorean.interior.

Reference: references/parts/interior/interior-cabin.png
           references/parts/doors/door-sill-jamb.png
"""
from __future__ import annotations

from delorean import interior
from delorean.interior import InteriorBuilder

from .harness import (TestContext, assert_within_bounds, standard_checks,
                      visual_test)

GROUP = "interior"

# Hard envelope every interior part must stay inside (see interior.py's
# module docstring / the task brief): nothing may poke outside the body.
LO = (-1.05, -0.86, 0.26)
HI = (0.50, 0.86, 1.12)


@visual_test("interior_tub", reference="interior/interior-cabin.png", group=GROUP)
def test_cabin_tub(ctx: TestContext) -> None:
    """Floor, side walls, firewall and rear bulkhead — the shell that stops
    you seeing straight through the car from one door aperture to the other."""
    tub = InteriorBuilder(ctx.materials).cabin_tub()

    standard_checks([tub])
    assert_within_bounds([tub], LO, HI, label="Int_Tub")

    ctx.render([tub], "interior_tub", view="top", margin=1.2,
               resolution=(900, 700))
    ctx.render([tub], "interior_tub_quarter", view="part_quarter", margin=1.3)


@visual_test("interior_door_sills", reference="doors/door-sill-jamb.png",
             group=GROUP)
def test_door_sills(ctx: TestContext) -> None:
    """The scuff-plate lip along the bottom of each door aperture."""
    sills = InteriorBuilder(ctx.materials).door_sills()

    standard_checks(sills)
    assert len(sills) == 2
    assert_within_bounds(sills, LO, HI, label="Int_DoorSill")

    ctx.render(sills, "interior_door_sills", view="part_quarter", margin=1.4)


@visual_test("interior_seats", reference="interior/interior-cabin.png",
             group=GROUP)
def test_seats(ctx: TestContext) -> None:
    """Two reclined bucket seats, ribbed backrests and headrests."""
    seats = InteriorBuilder(ctx.materials).seats()

    standard_checks(seats)
    assert len(seats) == 2
    assert_within_bounds(seats, LO, HI, label="Int_Seat")

    ctx.render(seats, "interior_seats", view="part_quarter", margin=1.2)
    ctx.render(seats, "interior_seats_top", view="top", margin=1.2)


@visual_test("interior_dashboard", reference="interior/interior-cabin.png",
             group=GROUP)
def test_dashboard(ctx: TestContext) -> None:
    """The dash pad sweeping across the firewall, with the driver's binnacle."""
    dash = InteriorBuilder(ctx.materials).dashboard()

    standard_checks([dash])
    assert_within_bounds([dash], LO, HI, label="Int_Dash")

    ctx.render([dash], "interior_dashboard", view="part_quarter", margin=1.3)


@visual_test("interior_steering_wheel", reference="interior/interior-cabin.png",
             group=GROUP)
def test_steering_wheel(ctx: TestContext) -> None:
    """Rim, spokes and boss, tilted back onto the column axis."""
    wheel = InteriorBuilder(ctx.materials).steering_wheel()

    standard_checks([wheel])
    assert_within_bounds([wheel], LO, HI, label="Int_SteeringWheel")

    d = InteriorBuilder.WHEEL_DIAMETER
    if wheel.dimensions.x > d * 1.6 or wheel.dimensions.z > d * 1.6:
        raise AssertionError(
            f"Int_SteeringWheel: bounding box {tuple(wheel.dimensions)} looks "
            f"far bigger than the {d} m diameter — likely a bad tilt")

    ctx.render([wheel], "interior_steering_wheel", view="part_quarter",
               margin=1.6)
    ctx.render([wheel], "interior_steering_wheel_side", view="side",
               margin=3.0)


@visual_test("interior_console", reference="interior/interior-cabin.png",
             group=GROUP)
def test_console(ctx: TestContext) -> None:
    """The transmission tunnel between the seats, with its gear lever."""
    console = InteriorBuilder(ctx.materials).console()

    standard_checks([console])
    assert_within_bounds([console], LO, HI, label="Int_Console")

    ctx.render([console], "interior_console", view="part_quarter", margin=1.4)


@visual_test("interior_full", reference="interior/interior-cabin.png",
             group=GROUP)
def test_full_interior(ctx: TestContext) -> None:
    """The whole cabin together — layout sanity from above, and a cabin shot
    at roughly the angle of interior-cabin.png."""
    parts = interior.build_interior(ctx.materials)

    standard_checks(parts)
    assert_within_bounds(parts, LO, HI, label="interior")

    names = {ob.name for ob in parts}
    for expected in ("Int_Tub", "Int_DoorSill_L", "Int_DoorSill_R",
                     "Int_Seat_L", "Int_Seat_R", "Int_Dash",
                     "Int_SteeringWheel", "Int_Console"):
        if expected not in names:
            raise AssertionError(f"missing expected object {expected!r}")

    ctx.render(parts, "interior_full_top", view="top", margin=1.15,
               resolution=(900, 700))
    ctx.render(parts, "interior_full_quarter", view="part_quarter", margin=1.6,
               resolution=(900, 700))
