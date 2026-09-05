"""Procedural material library.

No image textures, no HDRIs, no external assets — every surface is a node graph.
The DMC-12 wore no paint, so the headline material is bare brushed SS304: a
metal with strongly anisotropic reflection and a fine directional grain.
"""
from __future__ import annotations

import bpy

# Principled BSDF socket names moved between Blender versions; resolve by trying
# the modern name first and falling back.
_SOCKET_ALIASES = {
    "specular": ("Specular IOR Level", "Specular"),
    "transmission": ("Transmission Weight", "Transmission"),
    "emission_color": ("Emission Color", "Emission"),
    "emission_strength": ("Emission Strength",),
    "anisotropic": ("Anisotropic",),
    "coat": ("Coat Weight", "Clearcoat"),
    "coat_rough": ("Coat Roughness", "Clearcoat Roughness"),
}


def _set(node: bpy.types.Node, key: str, value) -> None:
    for name in _SOCKET_ALIASES.get(key, (key,)):
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


class MaterialLibrary:
    """Builds every material once and hands them out by key."""

    def __init__(self) -> None:
        self._mats: dict[str, bpy.types.Material] = {}
        self._build()

    def __getitem__(self, key: str) -> bpy.types.Material:
        return self._mats[key]

    def get(self, key: str) -> bpy.types.Material | None:
        return self._mats.get(key)

    @property
    def all(self) -> dict[str, bpy.types.Material]:
        return dict(self._mats)

    # ------------------------------------------------------------- primitives
    @staticmethod
    def _new(name: str) -> tuple[bpy.types.Material, bpy.types.Node]:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        return mat, mat.node_tree.nodes["Principled BSDF"]

    def _pbr(self, key: str, name: str, base: tuple[float, float, float],
             metallic: float = 0.0, roughness: float = 0.5,
             specular: float = 0.5) -> bpy.types.Material:
        mat, bsdf = self._new(name)
        bsdf.inputs["Base Color"].default_value = (*base, 1.0)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        _set(bsdf, "specular", specular)
        self._mats[key] = mat
        return mat

    def _emissive(self, key: str, name: str, colour: tuple[float, float, float],
                  strength: float = 0.0, roughness: float = 0.06,
                  transmission: float = 0.0) -> bpy.types.Material:
        mat, bsdf = self._new(name)
        bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        _set(bsdf, "transmission", transmission)
        _set(bsdf, "emission_color", (*colour, 1.0))
        _set(bsdf, "emission_strength", strength)
        self._mats[key] = mat
        return mat

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        self._brushed_stainless()
        self._black_urethane()
        self._glass()
        self._metals()
        self._lamps()
        self._rubber_and_cloth()

    def _brushed_stainless(self) -> None:
        """SS304 body panels: anisotropic, with a fine lengthwise grain."""
        mat, bsdf = self._new("SteelBrushed")
        bsdf.inputs["Base Color"].default_value = (0.560, 0.570, 0.585, 1.0)
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.255
        _set(bsdf, "anisotropic", 0.85)

        nt = mat.node_tree
        tex_co = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        bump = nt.nodes.new("ShaderNodeBump")

        # stretched hard along X so the grain runs fore-and-aft, as it does on
        # a rolled steel panel
        mapping.inputs["Scale"].default_value = (1.0, 900.0, 900.0)
        noise.inputs["Scale"].default_value = 4.0
        noise.inputs["Detail"].default_value = 2.0
        bump.inputs["Strength"].default_value = 0.09
        bump.inputs["Distance"].default_value = 0.0015

        nt.links.new(tex_co.outputs["Object"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

        for node, x, y in ((tex_co, -900, 0), (mapping, -700, 0),
                           (noise, -500, 0), (bump, -300, 0)):
            node.location = (x, y)
        self._mats["steel"] = mat

    def _black_urethane(self) -> None:
        """Bumpers and rocker mouldings: satin black with a fine grain."""
        mat, bsdf = self._new("BlackUrethane")
        bsdf.inputs["Base Color"].default_value = (0.019, 0.019, 0.021, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.52

        nt = mat.node_tree
        noise = nt.nodes.new("ShaderNodeTexNoise")
        bump = nt.nodes.new("ShaderNodeBump")
        noise.inputs["Scale"].default_value = 320.0
        noise.inputs["Detail"].default_value = 3.0
        bump.inputs["Strength"].default_value = 0.22
        bump.inputs["Distance"].default_value = 0.0008
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        noise.location = (-500, 0)
        bump.location = (-300, 0)
        self._mats["black"] = mat

        self._pbr("black_gloss", "BlackGloss", (0.012, 0.012, 0.013), 0.0, 0.14)
        self._pbr("black_matte", "BlackMatte", (0.016, 0.016, 0.018), 0.0, 0.72)

    def _glass(self) -> None:
        mat, bsdf = self._new("Glass")
        bsdf.inputs["Base Color"].default_value = (0.62, 0.66, 0.68, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.02
        bsdf.inputs["IOR"].default_value = 1.52
        _set(bsdf, "transmission", 0.92)
        mat.use_backface_culling = False
        self._mats["glass"] = mat

        # the backlight sits under the louvres and reads as near-black
        self._pbr("glass_dark", "GlassDark", (0.035, 0.038, 0.042), 0.0, 0.09)

    def _metals(self) -> None:
        self._pbr("chrome", "Chrome", (0.83, 0.84, 0.86), 1.0, 0.075)
        self._pbr("alloy", "AlloyPolished", (0.72, 0.73, 0.75), 1.0, 0.16)
        self._pbr("alloy_dark", "AlloyCast", (0.44, 0.45, 0.47), 1.0, 0.38)
        self._pbr("steel_dark", "SteelDark", (0.40, 0.41, 0.42), 1.0, 0.36)

    def _lamps(self) -> None:
        self._emissive("lens_clear", "LensClear", (0.85, 0.86, 0.88),
                       strength=0.0, roughness=0.04, transmission=0.55)
        self._emissive("lens_amber", "LensAmber", (0.85, 0.32, 0.02), 0.9)
        self._emissive("lens_red", "LensRed", (0.70, 0.03, 0.02), 0.7)
        self._emissive("lens_white", "LensWhite", (0.90, 0.90, 0.90), 0.2)
        self._emissive("headlamp", "HeadLamp", (0.95, 0.93, 0.86), 3.0,
                       roughness=0.03)
        self._pbr("reflector", "Reflector", (0.90, 0.90, 0.92), 1.0, 0.05)

    def _rubber_and_cloth(self) -> None:
        self._pbr("tyre", "Tyre", (0.026, 0.026, 0.028), 0.0, 0.72)
        self._pbr("rubber", "Rubber", (0.020, 0.020, 0.021), 0.0, 0.80)
        self._pbr("leather", "Leather", (0.048, 0.048, 0.052), 0.0, 0.48)
        self._pbr("carpet", "Carpet", (0.022, 0.022, 0.024), 0.0, 0.92)
        self._pbr("interior", "InteriorTrim", (0.030, 0.030, 0.033), 0.0, 0.62)
        self._pbr("ground", "Ground", (0.075, 0.076, 0.080), 0.0, 0.45)
        self._pbr("clay", "Clay", (0.42, 0.42, 0.43), 0.0, 0.62)


def apply_clay_override(library: MaterialLibrary,
                        objects: list[bpy.types.Object]) -> None:
    """Replace every material with flat grey, for shape-only metric renders."""
    clay = library["clay"]
    for ob in objects:
        if ob.type != 'MESH':
            continue
        ob.data.materials.clear()
        ob.data.materials.append(clay)
        for poly in ob.data.polygons:
            poly.material_index = 0
