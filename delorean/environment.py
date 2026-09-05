"""World environments.

Bare stainless is almost pure reflection, so what the car *reflects* matters
more than what the lamps do. Two environments are available:

`procedural`
    A luminance gradient — dark ground, bright band at the horizon, soft upper
    hemisphere. Neutral, deterministic, no assets.

`reference`
    Built from one of the committed reference photographs, so the model
    reflects the same surroundings that lit the real car.

Three honest caveats about using a photograph as an environment, and what this
module does about each:

* **It is LDR.** Highlights are clipped at white, so it cannot produce the
  bright speculars a true HDRI would. Mitigated by `highlight_boost`, which
  re-expands the top end of the range.
* **It is not a panorama.** A perspective photo mapped equirectangular puts
  the ground at the poles and stretches the edges. Mitigated by blending it
  against the procedural gradient, which supplies the correct vertical
  luminance structure while the photo supplies colour and variation.
* **It contains the car.** At low resolution and blended down this reads as
  plausible surroundings rather than a copy of the subject.

The blur is done by downscaling the image inside Blender — no external
dependency, and environment reflections are low-frequency anyway.
"""
from __future__ import annotations

import os

import bpy

REFERENCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references")

#: gravel courtyard at dusk — neutral, open sky, nothing lurid
DEFAULT_REFERENCE = "front-quarter-left-gravel.jpg"


def _clear(nt: bpy.types.NodeTree) -> None:
    nt.nodes.clear()


def _gradient(nt: bpy.types.NodeTree, x: int = -900) -> bpy.types.Node:
    """Dark ground, bright horizon band, soft sky. Returns the colour output."""
    tex = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")

    ramp.color_ramp.interpolation = 'EASE'
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.000, (0.030, 0.032, 0.036, 1.0)
    e[1].position, e[1].color = 0.470, (0.180, 0.190, 0.210, 1.0)
    band = ramp.color_ramp.elements.new(0.520)
    band.color = (1.400, 1.450, 1.520, 1.0)
    upper = ramp.color_ramp.elements.new(0.630)
    upper.color = (0.780, 0.820, 0.900, 1.0)
    zenith = ramp.color_ramp.elements.new(1.000)
    zenith.color = (1.050, 1.100, 1.200, 1.0)

    nt.links.new(tex.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    for node, dx in ((tex, 0), (sep, 200), (ramp, 400)):
        node.location = (x + dx, 300)
    return ramp


def load_reference_image(filename: str, blur_width: int = 256) -> bpy.types.Image:
    """Load a reference and downscale it — the downscale *is* the blur."""
    path = os.path.join(REFERENCE_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    key = f"env_{os.path.splitext(filename)[0]}_{blur_width}"
    existing = bpy.data.images.get(key)
    if existing is not None:
        return existing

    img = bpy.data.images.load(path, check_existing=False)
    img.name = key
    # 2:1 so it maps sanely as equirectangular
    img.scale(blur_width, max(2, blur_width // 2))
    # bake the pixels so nothing reloads from disk at full resolution
    img.pack()
    return img


def _highlight_boost(nt: bpy.types.NodeTree, colour_socket,
                     threshold: float = 0.55, amount: float = 6.0,
                     x: int = -400) -> bpy.types.NodeSocket:
    """Re-expand clipped highlights, so an LDR photo can still throw speculars."""
    luma = nt.nodes.new("ShaderNodeRGBToBW")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    scale = nt.nodes.new("ShaderNodeMath")
    plus_one = nt.nodes.new("ShaderNodeMath")
    mul = nt.nodes.new("ShaderNodeVectorMath")

    ramp.color_ramp.interpolation = 'EASE'
    ramp.color_ramp.elements[0].position = threshold
    ramp.color_ramp.elements[1].position = 1.0
    scale.operation = 'MULTIPLY'
    scale.inputs[1].default_value = amount
    plus_one.operation = 'ADD'
    plus_one.inputs[1].default_value = 1.0
    mul.operation = 'SCALE'

    nt.links.new(colour_socket, luma.inputs["Color"])
    nt.links.new(luma.outputs["Val"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], scale.inputs[0])
    nt.links.new(scale.outputs["Value"], plus_one.inputs[0])
    nt.links.new(colour_socket, mul.inputs[0])
    nt.links.new(plus_one.outputs["Value"], mul.inputs["Scale"])

    for i, node in enumerate((luma, ramp, scale, plus_one, mul)):
        node.location = (x + i * 190, -220)
    return mul.outputs["Vector"]


class Environment:
    """Builds the world shader.

    `backdrop` overrides what the *camera* sees without touching what the model
    reflects, which is how a part can sit on a flat blueprint-blue field while
    still being lit by a full studio.
    """

    def __init__(self, strength: float = 1.0,
                 backdrop: tuple[float, float, float, float] | None = None) -> None:
        self.strength = strength
        self.backdrop = backdrop

    # ------------------------------------------------------------------ world
    def _world(self) -> tuple[bpy.types.World, bpy.types.NodeTree]:
        world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
        bpy.context.scene.world = world
        world.use_nodes = True
        _clear(world.node_tree)
        return world, world.node_tree

    def _finish(self, nt: bpy.types.NodeTree, colour_socket) -> None:
        """Wire a colour into the world output, honouring `backdrop`."""
        env_bg = nt.nodes.new("ShaderNodeBackground")
        env_bg.inputs["Strength"].default_value = self.strength
        nt.links.new(colour_socket, env_bg.inputs["Color"])
        env_bg.location = (200, 200)

        out = nt.nodes.new("ShaderNodeOutputWorld")
        out.location = (700, 100)

        if self.backdrop is None:
            nt.links.new(env_bg.outputs["Background"], out.inputs["Surface"])
            return

        flat = nt.nodes.new("ShaderNodeBackground")
        flat.inputs["Color"].default_value = self.backdrop
        flat.inputs["Strength"].default_value = 1.0
        flat.location = (200, -80)

        path = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        path.location = (200, 520)
        mix.location = (470, 100)

        # fac 0 -> environment (reflections, lighting); fac 1 -> flat backdrop
        nt.links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
        nt.links.new(env_bg.outputs["Background"], mix.inputs[1])
        nt.links.new(flat.outputs["Background"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])

    # ------------------------------------------------------------- flavours
    def procedural(self) -> bpy.types.World:
        world, nt = self._world()
        ramp = _gradient(nt)
        self._finish(nt, ramp.outputs["Color"])
        return world

    def from_reference(self, filename: str = DEFAULT_REFERENCE,
                       photo_mix: float = 0.62, rotation_deg: float = 0.0,
                       blur_width: int = 256, highlight_boost: float = 6.0
                       ) -> bpy.types.World:
        """Photo colour over the gradient's luminance structure."""
        try:
            image = load_reference_image(filename, blur_width=blur_width)
        except FileNotFoundError:
            return self.procedural()

        world, nt = self._world()

        tex_co = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = image
        env.projection = 'EQUIRECTANGULAR'
        env.interpolation = 'Cubic'
        mapping.inputs["Rotation"].default_value = (
            0.0, 0.0, __import__("math").radians(rotation_deg))
        nt.links.new(tex_co.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
        for i, node in enumerate((tex_co, mapping, env)):
            node.location = (-1300 + i * 220, -80)

        boosted = _highlight_boost(nt, env.outputs["Color"],
                                   amount=highlight_boost)

        ramp = _gradient(nt)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = 'RGBA'
        mix.blend_type = 'MIX'
        mix.inputs["Factor"].default_value = photo_mix
        mix.location = (-100, 60)

        nt.links.new(ramp.outputs["Color"], mix.inputs[6])     # A
        nt.links.new(boosted, mix.inputs[7])                   # B
        self._finish(nt, mix.outputs[2])
        return world
