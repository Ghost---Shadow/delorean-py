"""Isolated rendering, for fast iteration on one part at a time.

The viewport equivalent is local view (numpad `/`). Rendering the whole car to
check a tail lamp costs minutes per iteration; isolating the part, framing it
tightly and rendering small costs seconds. Use it liberally.

    with isolate(wheel_parts):
        render("renders/parts/wheel.png", resolution=(700, 700), samples=24)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterable, Iterator, Sequence

import bpy

#: object name prefixes that stay visible even when isolating (the set dressing
#: an object needs in order to be lit and to cast onto something)
KEEP_VISIBLE = ("Camera", "CameraTarget", "Key", "Fill", "Rim", "Strip",
                "Softbox_")


def _renderable() -> list[bpy.types.Object]:
    return [ob for ob in bpy.data.objects if ob.type in {'MESH', 'CURVE', 'FONT'}]


@contextmanager
def isolate(keep: Sequence[bpy.types.Object],
            keep_ground: bool = False) -> Iterator[None]:
    """Hide everything from the render except `keep` (and the lights)."""
    names = {ob.name for ob in keep}
    if keep_ground:
        names.add("Ground")

    previous: dict[str, bool] = {}
    for ob in _renderable():
        previous[ob.name] = ob.hide_render
        if ob.name.startswith(KEEP_VISIBLE):
            continue
        ob.hide_render = ob.name not in names
    try:
        yield
    finally:
        for name, state in previous.items():
            ob = bpy.data.objects.get(name)
            if ob is not None:
                ob.hide_render = state


def find(*patterns: str) -> list[bpy.types.Object]:
    """Objects whose name contains any of the given substrings."""
    out: list[bpy.types.Object] = []
    for ob in bpy.data.objects:
        if any(p.lower() in ob.name.lower() for p in patterns):
            out.append(ob)
    return out


def render(path: str, resolution: tuple[int, int] | None = None,
           samples: int | None = None) -> str:
    """Render the current camera to `path`, restoring settings afterwards."""
    scn = bpy.context.scene
    r = scn.render
    saved = (r.filepath, r.resolution_x, r.resolution_y)
    is_cycles = r.engine == 'CYCLES'
    saved_samples = (scn.cycles.samples if is_cycles
                     else getattr(scn.eevee, "taa_render_samples", None))

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if resolution:
        r.resolution_x, r.resolution_y = resolution
    if samples is not None:
        if is_cycles:
            scn.cycles.samples = samples
        elif hasattr(scn.eevee, "taa_render_samples"):
            scn.eevee.taa_render_samples = samples
    r.filepath = os.path.abspath(path)

    try:
        bpy.ops.render.render(write_still=True)
    finally:
        r.filepath, r.resolution_x, r.resolution_y = saved
        if saved_samples is not None:
            if is_cycles:
                scn.cycles.samples = saved_samples
            else:
                scn.eevee.taa_render_samples = saved_samples
    return os.path.abspath(path)


def preview_part(scene_builder, objects: Iterable[bpy.types.Object], path: str,
                 view: str = "hero_front_left", margin: float = 1.15,
                 resolution: tuple[int, int] = (800, 800),
                 samples: int = 24, keep_ground: bool = False) -> str:
    """Frame a subset of the model tightly and render it on its own."""
    objects = list(objects)
    if not objects:
        raise ValueError("preview_part: nothing to preview")

    scene_builder.apply_view(view)
    scene_builder.frame_objects(objects, margin=margin)
    with isolate(objects, keep_ground=keep_ground):
        return render(path, resolution=resolution, samples=samples)
