"""Visual unit tests for delorean.wheels.

Reference: references/parts/wheels/wheel-front-turbine.png
"""
from __future__ import annotations

import math

from delorean import config as cfg
from delorean import mesh_utils as mu
from delorean import wheels
from delorean.wheels import WheelBuilder

from .harness import (TestContext, assert_dimensions, standard_checks,
                      visual_test)

GROUP = "wheels"


@visual_test("wheel_front_tyre", reference="wheels/wheel-front-turbine.png",
             group=GROUP)
def test_front_tyre(ctx: TestContext) -> None:
    """195/60R14 tyre alone: 589.6 mm across, 195 mm section."""
    spec = cfg.WHEEL_FRONT
    tyre = WheelBuilder(ctx.materials).tyre("Wheel_FL_Tyre", spec)

    standard_checks([tyre])
    d = spec.radius * 2.0
    assert_dimensions(tyre, (d, spec.width, d), tol=0.008)

    ctx.render([tyre], "wheel_front_tyre", view="part_quarter")


@visual_test("wheel_front_rim", reference="wheels/wheel-front-hires.png",
             group=GROUP)
def test_front_rim(ctx: TestContext) -> None:
    """The turbine face: 44 spokes, polished lip, five lugs, centre cap."""
    spec = cfg.WHEEL_FRONT
    rim = WheelBuilder(ctx.materials).rim("Wheel_FL_Rim", spec)

    standard_checks([rim])
    # the rim must live inside the bead, not poke through the tyre
    assert_dimensions(rim, (spec.bead_radius * 2.0, None,
                            spec.bead_radius * 2.0), tol=0.01)

    # straight down the axle, which is how the reference crop sees it
    ctx.render([rim], "wheel_front_rim", view="part_face_ortho", margin=1.04)
    ctx.render([rim], "wheel_front_rim_quarter", view="part_quarter")


@visual_test("wheel_front_assembled", reference="wheels/wheel-front-turbine.png",
             group=GROUP)
def test_front_assembled(ctx: TestContext) -> None:
    """Tyre and rim together — checks the rim does not float inside the bead."""
    spec = cfg.WHEEL_FRONT
    builder = WheelBuilder(ctx.materials)
    parts = builder.corner("FL", spec, (0.0, 0.0, spec.radius), mirrored=False)

    standard_checks(parts)
    ctx.render(parts, "wheel_front_assembled", view="part_quarter")
    ctx.render(parts, "wheel_front_assembled_face", view="part_face_ortho",
               margin=1.04)


@visual_test("wheel_rear_assembled", reference="wheels/wheel-rear-turbine.png",
             group=GROUP)
def test_rear_assembled(ctx: TestContext) -> None:
    """235/60R15: visibly fatter and taller than the front."""
    spec = cfg.WHEEL_REAR
    builder = WheelBuilder(ctx.materials)
    parts = builder.corner("RL", spec, (0.0, 0.0, spec.radius), mirrored=False)

    standard_checks(parts)
    d = spec.radius * 2.0
    assert_dimensions(parts[0], (d, spec.width, d), tol=0.008)
    ctx.render(parts, "wheel_rear_assembled", view="part_quarter")


@visual_test("wheel_set_layout", group=GROUP)
def test_wheel_set(ctx: TestContext) -> None:
    """All four corners on their axles, sitting exactly on Z=0."""
    parts = wheels.build_wheels(ctx.materials, cfg.RigConfig())

    standard_checks(parts)
    assert len(parts) == 8, f"expected 8 objects (4 corners x 2), got {len(parts)}"

    mu.sync()
    for ob in parts:
        lowest = min((ob.matrix_world @ v.co).z for v in ob.data.vertices)
        if lowest < -0.002:
            raise AssertionError(f"{ob.name} sinks {-lowest*1000:.1f} mm below ground")

    tyres = [o for o in parts if o.name.endswith("Tyre")]
    lowest = min(min((o.matrix_world @ v.co).z for v in o.data.vertices)
                 for o in tyres)
    if lowest > 0.003:
        raise AssertionError(f"wheels float {lowest*1000:.1f} mm above ground")

    ctx.render(parts, "wheel_set_layout", view="hero_front_left", margin=1.1,
               resolution=(900, 620), keep_ground=True)


@visual_test("wheel_steering_pose", group=GROUP)
def test_steering(ctx: TestContext) -> None:
    """Steering angle must move only the front wheels."""
    rig = cfg.RigConfig(steer_deg=22.0)
    parts = wheels.build_wheels(ctx.materials, rig)

    for ob in parts:
        tag = ob.name.split("_")[1]
        expected = math.radians(22.0) if tag.startswith("F") else 0.0
        if abs(ob.rotation_euler.z - expected) > 1e-6:
            raise AssertionError(
                f"{ob.name}: steer {math.degrees(ob.rotation_euler.z):.1f} deg, "
                f"expected {math.degrees(expected):.1f}")

    ctx.render(parts, "wheel_steering_pose", view="top", margin=1.1,
               resolution=(900, 620))
