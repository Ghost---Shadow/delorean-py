"""Visual unit tests for delorean.trim.

Reference: references/parts/trim/louvres-backlight.png (+ mirror-door.png,
grille-dmc-badge.png, rear-bumper-badge.png, exhaust-tips.png)
"""
from __future__ import annotations

from delorean import config as cfg
from delorean import mesh_utils as mu
from delorean import trim
from delorean.trim import TrimBuilder

from .harness import (TestContext, assert_within_bounds, standard_checks,
                      visual_test)

GROUP = "trim"


@visual_test("trim_louvres", reference="trim/louvres-backlight.png", group=GROUP)
def test_louvres(ctx: TestContext) -> None:
    """12 tilted slats plus a frame, following the fastback skin."""
    parts = TrimBuilder(ctx.materials).louvres()

    standard_checks(parts)
    slats = [p for p in parts if "Slat" in p.name]
    if len(slats) not in range(11, 14):
        raise AssertionError(f"expected 11-13 slats, got {len(slats)}")

    # the whole assembly must sit inside the backlight's own footprint, with
    # a little headroom for the offset above the skin
    assert_within_bounds(
        parts,
        lo=(TrimBuilder.LOUVRE_X0 - 0.03, None, None),
        hi=(TrimBuilder.LOUVRE_X1 + 0.03, None, 1.20),
        label="Trim_Louvre")

    ctx.render(parts, "trim_louvres", view="hero_rear_right", margin=1.3,
               resolution=(900, 700))
    ctx.render(parts, "trim_louvres_quarter", view="part_quarter", margin=1.25)


@visual_test("trim_mirror", reference="trim/mirror-door.png", group=GROUP)
def test_mirror(ctx: TestContext) -> None:
    """One housing + stalk + glass per side, mirrored about Y."""
    parts = TrimBuilder(ctx.materials).mirrors()

    standard_checks(parts)
    if len(parts) != 2:
        raise AssertionError(f"expected 2 mirror objects (L/R), got {len(parts)}")

    mu.sync()
    left, _right = parts
    ctx.render(parts, "trim_mirror", view="part_quarter", margin=1.4)
    ctx.render([left], "trim_mirror_left", view="side", margin=1.6,
               resolution=(700, 500))


@visual_test("trim_grille_badge", reference="trim/grille-dmc-badge.png", group=GROUP)
def test_grille_badge(ctx: TestContext) -> None:
    """The "DMC" lettering on the nose, converted to a solid mesh."""
    parts = TrimBuilder(ctx.materials).grille_badge()

    standard_checks(parts)
    badge = parts[0]
    if badge.type != 'MESH':
        raise AssertionError(f"{badge.name}: still a {badge.type}, not converted")

    ctx.render(parts, "trim_grille_badge", view="front", margin=1.8,
               resolution=(700, 500))


@visual_test("trim_rear_badge", reference="trim/rear-bumper-badge.png", group=GROUP)
def test_rear_badge(ctx: TestContext) -> None:
    """The "DE LOREAN" lettering on the tail, offset to the driver's side."""
    parts = TrimBuilder(ctx.materials).rear_badge()

    standard_checks(parts)
    badge = parts[0]
    if badge.type != 'MESH':
        raise AssertionError(f"{badge.name}: still a {badge.type}, not converted")
    if badge.matrix_world.translation.y <= 0.0:
        raise AssertionError("rear badge should be offset to +Y (driver's side)")

    ctx.render(parts, "trim_rear_badge", view="rear", margin=1.8,
               resolution=(700, 500))


@visual_test("trim_exhaust", reference="trim/exhaust-tips.png", group=GROUP)
def test_exhaust(ctx: TestContext) -> None:
    """Two tips, symmetric about the centreline, tucked under the bumper."""
    parts = TrimBuilder(ctx.materials).exhaust_tips()

    standard_checks(parts)
    if len(parts) != 2:
        raise AssertionError(f"expected 2 exhaust tips, got {len(parts)}")

    ctx.render(parts, "trim_exhaust", view="rear", margin=2.2,
               resolution=(800, 500))


@visual_test("trim_rear_plate", group=GROUP)
def test_rear_plate(ctx: TestContext) -> None:
    """A flat recessed panel, centred on the tail."""
    parts = TrimBuilder(ctx.materials).rear_plate()

    standard_checks(parts)
    assert_within_bounds(parts, lo=(None, -0.16, None), hi=(None, 0.16, None))

    ctx.render(parts, "trim_rear_plate", view="rear", margin=1.8,
               resolution=(700, 500))


@visual_test("trim_full_car", group=GROUP)
def test_build_trim(ctx: TestContext) -> None:
    """Every trim piece together, on the whole-car hero framing."""
    parts = trim.build_trim(ctx.materials)

    standard_checks(parts)
    # every object must be within the published half-length/half-width
    # the louvre sits proud of the roof skin by its z-offset, so a slat near
    # the roof peak legitimately pokes a few mm above the nominal height
    assert_within_bounds(
        parts, lo=(-cfg.LENGTH / 2 - 0.02, -cfg.WIDTH / 2, 0.0),
        hi=(cfg.LENGTH / 2 + 0.02, cfg.WIDTH / 2, cfg.HEIGHT + 0.05))

    for ob in parts:
        if not ob.name.startswith("Trim_"):
            raise AssertionError(f"{ob.name}: missing Trim_ prefix")

    ctx.render(parts, "trim_full_car", view="hero_rear_right", margin=1.15,
               resolution=(1000, 700))
    ctx.render(parts, "trim_full_car_front", view="hero_front_left", margin=1.15,
               resolution=(1000, 700))
