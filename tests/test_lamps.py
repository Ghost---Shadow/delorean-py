"""Visual unit tests for delorean.lamps.

References: references/parts/lamps/nose-fascia.png (front),
            references/parts/lamps/tail-panel-full.png (rear).
"""
from __future__ import annotations

from delorean import lamps
from delorean.lamps import LampBuilder

from .harness import TestContext, assert_dimensions, standard_checks, visual_test

GROUP = "lamps"


@visual_test("lamp_headlamp_pair", reference="lamps/headlamp-outer-pair.png",
             group=GROUP)
def test_headlamp_pair(ctx: TestContext) -> None:
    """One side's inner + outer sealed-beam units, side by side in the fascia."""
    builder = LampBuilder(ctx.materials)
    inner = builder.headlamp("FL", "inner", 1.0)
    outer = builder.headlamp("FL", "outer", 1.0)
    parts = [inner, outer]

    standard_checks(parts)
    for ob in parts:
        assert_dimensions(ob, (None, builder.HEAD_W, builder.HEAD_H), tol=0.01)

    ctx.render(parts, "lamp_headlamp_pair", view="front", margin=1.3)
    ctx.render(parts, "lamp_headlamp_pair_quarter", view="hero_front_left",
               margin=1.3)


@visual_test("lamp_grille", group=GROUP)
def test_grille(ctx: TestContext) -> None:
    """The centre grille: eleven horizontal slats over a black backing."""
    builder = LampBuilder(ctx.materials)
    grille = builder.grille()

    standard_checks([grille])
    assert_dimensions(grille, (None, 2.0 * builder.GRILLE_HALF_W,
                               builder.FASCIA_Z1 - builder.FASCIA_Z0), tol=0.01)

    ctx.render([grille], "lamp_grille", view="front", margin=1.3)


@visual_test("lamp_front_fascia", reference="lamps/nose-fascia.png", group=GROUP)
def test_front_fascia(ctx: TestContext) -> None:
    """Grille, four headlamps and both indicators, assembled and mirrored."""
    builder = LampBuilder(ctx.materials)
    parts = [builder.grille()]
    for sign, tag in ((1.0, "FL"), (-1.0, "FR")):
        parts.append(builder.headlamp(tag, "inner", sign))
        parts.append(builder.headlamp(tag, "outer", sign))
        parts.append(builder.indicator(tag, sign))

    standard_checks(parts)
    ctx.render(parts, "lamp_front_fascia", view="hero_front_left", margin=1.2)
    ctx.render(parts, "lamp_front_fascia_face", view="front", margin=1.2)


@visual_test("lamp_front_marker", reference="lamps/marker-front-fender.png",
             group=GROUP)
def test_front_marker(ctx: TestContext) -> None:
    """Amber marker lamps set into the front fender flanks, both sides."""
    builder = LampBuilder(ctx.materials)
    parts = [builder.front_marker("FL", 1.0), builder.front_marker("FR", -1.0)]

    standard_checks(parts)
    ctx.render(parts, "lamp_front_marker", view="side", margin=1.6)


@visual_test("lamp_tail_cluster_left", reference="lamps/taillamp-left.png",
             group=GROUP)
def test_tail_cluster_left(ctx: TestContext) -> None:
    """Left taillamp cluster: outboard-to-inboard amber, red, red, clear."""
    builder = LampBuilder(ctx.materials)
    cluster = builder.tail_cluster("L", 1.0)

    standard_checks([cluster])
    ctx.render([cluster], "lamp_tail_cluster_left", view="rear", margin=1.3)


@visual_test("lamp_tail_cluster_right", reference="lamps/taillamp-right.png",
             group=GROUP)
def test_tail_cluster_right(ctx: TestContext) -> None:
    """Right taillamp cluster -- mirror of the left, same column order."""
    builder = LampBuilder(ctx.materials)
    cluster = builder.tail_cluster("R", -1.0)

    standard_checks([cluster])
    ctx.render([cluster], "lamp_tail_cluster_right", view="rear", margin=1.3)


@visual_test("lamp_tail_full", reference="lamps/tail-panel-full.png", group=GROUP)
def test_tail_full(ctx: TestContext) -> None:
    """Both clusters and the black panel they sit in, with the plate gap
    between them.
    """
    builder = LampBuilder(ctx.materials)
    parts = [builder.tail_panel(),
             builder.tail_cluster("L", 1.0),
             builder.tail_cluster("R", -1.0)]

    standard_checks(parts)
    ctx.render(parts, "lamp_tail_full", view="rear", margin=1.15)
    ctx.render(parts, "lamp_tail_full_quarter", view="hero_rear_left", margin=1.2)


@visual_test("lamp_rear_marker", group=GROUP)
def test_rear_marker(ctx: TestContext) -> None:
    """Red marker lamps set into the rear fender flanks, both sides."""
    builder = LampBuilder(ctx.materials)
    parts = [builder.rear_marker("L", 1.0), builder.rear_marker("R", -1.0)]

    standard_checks(parts)
    ctx.render(parts, "lamp_rear_marker", view="side", margin=1.6)


@visual_test("lamp_set_full", group=GROUP)
def test_lamp_set(ctx: TestContext) -> None:
    """Every lamp the module produces, named and mirrored correctly."""
    parts = lamps.build_lamps(ctx.materials)

    standard_checks(parts)
    for ob in parts:
        assert ob.name.startswith("Lamp_"), f"{ob.name}: missing Lamp_ prefix"

    names = {ob.name for ob in parts}
    expected = {
        "Lamp_Grille", "Lamp_Tail_Panel",
        "Lamp_Head_FL_Inner", "Lamp_Head_FL_Outer",
        "Lamp_Head_FR_Inner", "Lamp_Head_FR_Outer",
        "Lamp_Indicator_FL", "Lamp_Indicator_FR",
        "Lamp_Marker_Front_FL", "Lamp_Marker_Front_FR",
        "Lamp_Tail_L", "Lamp_Tail_R",
        "Lamp_Marker_Rear_L", "Lamp_Marker_Rear_R",
    }
    missing = expected - names
    assert not missing, f"missing lamp objects: {missing}"

    ctx.render(parts, "lamp_set_front", view="hero_front_left", margin=1.15,
               resolution=(900, 620))
    ctx.render(parts, "lamp_set_rear", view="hero_rear_left", margin=1.15,
               resolution=(900, 620))
