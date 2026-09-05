"""Camera, lighting, ground and render settings.

Bare stainless steel is almost entirely reflection, so it needs an environment
to reflect. Rather than an HDRI, the world is a procedural gradient plus a few
large emissive softboxes — enough to draw the long, soft highlights that make
brushed metal read as metal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import bpy
from mathutils import Vector

from . import config as cfg
from . import mesh_utils as mu
from .environment import Environment


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(hex_str: str, scale: float = 1.0) -> tuple[float, float, float, float]:
    """An sRGB hex string as a linear RGBA tuple, for node colour inputs."""
    h = hex_str.lstrip("#")
    vals = [srgb_to_linear(int(h[i:i + 2], 16) / 255.0) * scale
            for i in (0, 2, 4)]
    return (*vals, 1.0)


#: blueprint blue — dark parts on a black backdrop are unreadable, and this is
#: the traditional colour for looking at a shape rather than a photograph
BACKDROP_BLUEPRINT = "#6495ED"      # cornflower


@dataclass(frozen=True)
class View:
    """A camera placement, in orbital terms around a look-at point."""

    azimuth: float          # degrees, 0 = +X (behind the car), 180 = the nose
    elevation: float        # degrees above the horizon
    distance: float         # metres from the target
    target: tuple[float, float, float] = (0.0, 0.0, 0.62)
    lens: float = 70.0
    ortho: bool = False
    ortho_scale: float = 5.0


# Azimuth is measured about +Z from the +X axis. The nose points -X and the
# car's left is +Y, so a view of the front and the car's left flank sits
# between 90 and 180 degrees. Getting this backwards names every hero shot
# after the wrong side of the car.
VIEWS: dict[str, View] = {
    "hero_front_left":  View(145.0, 10.0, 11.0, lens=78.0),
    "hero_front_right": View(215.0, 10.0, 11.0, lens=78.0),
    "hero_rear_left":   View( 35.0, 13.0, 11.0, lens=78.0),
    "hero_rear_right":  View(325.0, 13.0, 11.0, lens=78.0),
    "front":            View(180.0,  4.0, 14.0, lens=110.0),
    "rear":             View(  0.0,  4.0, 14.0, lens=110.0),
    "side":             View( 90.0,  0.0, 16.0, ortho=True, ortho_scale=4.8),
    "side_right":       View(270.0,  0.0, 16.0, ortho=True, ortho_scale=4.8),
    "top":              View( 90.0, 89.5, 16.0, ortho=True, ortho_scale=4.8),
    "ortho_front":      View(180.0,  0.0, 16.0, ortho=True, ortho_scale=2.4),

    # part inspection. A wheel's visible face points +Y, so these look from the
    # +Y side; the hero views are all on -Y and would show its back.
    "part_quarter":     View( 52.0, 18.0,  4.0, lens=85.0, target=(0, 0, 0)),
    "part_face":        View( 90.0,  2.0,  4.0, lens=110.0, target=(0, 0, 0)),
    "part_face_ortho":  View( 90.0,  0.0,  6.0, target=(0, 0, 0),
                             ortho=True, ortho_scale=0.7),
    "part_top":         View( 52.0, 78.0,  4.0, lens=85.0, target=(0, 0, 0)),
}


class SceneBuilder:
    """Assembles the world, lights, ground and camera rig."""

    GROUND_SIZE = 80.0

    def __init__(self, materials, build: cfg.BuildConfig,
                 world_strength: float | None = None,
                 backdrop: str | None = None) -> None:
        self.materials = materials
        self.build_cfg = build
        self.world_strength = (build.environment_strength
                               if world_strength is None else world_strength)
        self.backdrop = backdrop if backdrop is not None else build.backdrop
        self.camera: bpy.types.Object | None = None
        self.target: bpy.types.Object | None = None

    # ----------------------------------------------------------------- world
    def world(self) -> None:
        """Build the world shader from the build config."""
        backdrop = None
        if self.backdrop is not None:
            backdrop = rgb(self.backdrop)

        env = Environment(strength=self.world_strength, backdrop=backdrop)
        cfgb = self.build_cfg
        if cfgb.environment == "hdri":
            from .environment import HDRI_PRESETS
            name = HDRI_PRESETS.get(cfgb.environment_hdri,
                                    cfgb.environment_hdri)
            env.hdri(name, rotation_deg=cfgb.environment_rotation_deg)
        elif cfgb.environment == "reference":
            env.from_reference(cfgb.environment_reference,
                               photo_mix=cfgb.environment_photo_mix,
                               rotation_deg=cfgb.environment_rotation_deg)
        else:
            env.procedural()

    # ---------------------------------------------------------------- lights
    def lights(self) -> list[bpy.types.Object]:
        """A key, a fill, a rim and a long overhead strip for the flanks."""
        specs = (
            # name,      type,   location,             energy, size,  rot(deg)
            ("Key",   'AREA', (-4.2, -5.0, 5.4),  600.0, 6.0, (38, 0, -40)),
            ("Fill",  'AREA', ( 5.2, -5.6, 3.2),  180.0, 6.0, (62, 0,  42)),
            ("Rim",   'AREA', ( 4.4,  6.0, 3.8),  320.0, 5.0, (58, 0, 200)),
            ("Strip", 'AREA', ( 0.0,  0.0, 4.6),  260.0, 1.0, (0, 0, 0)),
        )
        out = []
        for name, kind, loc, energy, size, rot in specs:
            data = bpy.data.lights.new(name, kind)
            data.energy = energy
            data.size = size
            if name == "Strip":
                # a softbox strip running the length of the car, so the flanks
                # get one continuous highlight rather than four hotspots
                data.shape = 'RECTANGLE'
                data.size = 7.0
                data.size_y = 1.6
            ob = bpy.data.objects.new(name, data)
            ob.location = loc
            ob.rotation_euler = tuple(math.radians(a) for a in rot)
            mu.link(ob)
            out.append(ob)
        return out

    # -------------------------------------------------------------- softboxes
    #: name, size (w, h), centre, euler (deg), emission strength
    SOFTBOXES = (
        ("Softbox_Top",   (7.0, 2.4), ( 0.00,  0.10, 4.30), (  0,  0,   0), 18.0),
        ("Softbox_Left",  (5.0, 2.6), (-1.20, -4.20, 2.40), ( 74,  0,  -6), 12.0),
        ("Softbox_Right", (4.2, 2.2), ( 1.60,  4.10, 2.30), (-74,  0,   4),  9.0),
        ("Softbox_Nose",  (2.6, 1.8), (-4.60, -1.10, 1.90), ( 68,  0, -68),  7.0),
    )

    def softboxes(self) -> list[bpy.types.Object]:
        """Large emitters, reflected by the car but invisible to the camera.

        This is the whole trick to a convincing bare-metal render. Point lamps
        give a flat sheen; a big rectangular emitter gives the long, hard-edged
        streak that reads as polished steel. They are hidden from camera rays
        so they light and reflect without appearing in the frame.
        """
        made: list[bpy.types.Object] = []
        for name, (w, h), loc, rot_deg, strength in self.SOFTBOXES:
            hw, hh = w / 2.0, h / 2.0
            plane = mu.obj_from_pydata(
                name,
                [(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0)],
                [(0, 1, 2, 3)])
            plane.location = loc
            plane.rotation_euler = tuple(math.radians(a) for a in rot_deg)

            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            nt = mat.node_tree
            nt.nodes.clear()
            emit = nt.nodes.new("ShaderNodeEmission")
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            emit.inputs["Color"].default_value = (1.0, 0.99, 0.97, 1.0)
            emit.inputs["Strength"].default_value = strength
            nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
            mu.set_material(plane, mat)

            self._set_many(plane, (("visible_camera", False),
                                   ("visible_shadow", False)))
            made.append(plane)
        return made

    # ---------------------------------------------------------------- ground
    def ground(self) -> bpy.types.Object:
        s = self.GROUND_SIZE / 2.0
        plane = mu.obj_from_pydata(
            "Ground",
            [(-s, -s, 0.0), (s, -s, 0.0), (s, s, 0.0), (-s, s, 0.0)],
            [(0, 1, 2, 3)])
        # Under an HDRI the floor is part of the photograph, so a grey plane
        # over it just hides the environment. Keep it as a shadow catcher: it
        # takes the contact shadow that grounds the car and is otherwise
        # invisible.
        if self.build_cfg.environment == "hdri":
            mu.set_material(plane, self.materials["ground"])
            self._set_many(plane, (("is_shadow_catcher", True),))
        else:
            mu.set_material(plane, self.materials["ground"])
        return plane

    # ---------------------------------------------------------------- camera
    def camera_rig(self) -> bpy.types.Object:
        target = bpy.data.objects.new("CameraTarget", None)
        target.empty_display_size = 0.2
        mu.link(target)

        data = bpy.data.cameras.new("Camera")
        cam = bpy.data.objects.new("Camera", data)
        mu.link(cam)

        track = cam.constraints.new('TRACK_TO')
        track.target = target
        track.track_axis = 'TRACK_NEGATIVE_Z'
        track.up_axis = 'UP_Y'

        bpy.context.scene.camera = cam
        self.camera, self.target = cam, target
        return cam

    def apply_view(self, view: View | str) -> None:
        if isinstance(view, str):
            view = VIEWS[view]
        if self.camera is None:
            self.camera_rig()

        cam, tgt = self.camera, self.target
        tgt.location = view.target

        az, el = math.radians(view.azimuth), math.radians(view.elevation)
        d = view.distance
        cam.location = (
            view.target[0] + d * math.cos(el) * math.cos(az),
            view.target[1] + d * math.cos(el) * math.sin(az),
            view.target[2] + d * math.sin(el),
        )
        cam.data.type = 'ORTHO' if view.ortho else 'PERSP'
        cam.data.lens = view.lens
        cam.data.ortho_scale = view.ortho_scale

    def frame_objects(self, objects: list[bpy.types.Object],
                      margin: float = 1.18) -> None:
        """Pull the camera in so `objects` fill the frame."""
        if self.camera is None or not objects:
            return
        pts: list[Vector] = []
        for ob in objects:
            if ob.type != 'MESH':
                continue
            for corner in ob.bound_box:
                pts.append(ob.matrix_world @ Vector(corner))
        if not pts:
            return

        centre = sum(pts, Vector()) / len(pts)
        radius = max((p - centre).length for p in pts) * margin

        cam = self.camera
        self.target.location = centre
        direction = (cam.location - centre)
        if direction.length < 1e-6:
            direction = Vector((1.0, -1.0, 0.4))
        direction.normalize()

        if cam.data.type == 'ORTHO':
            cam.data.ortho_scale = radius * 2.0
            cam.location = centre + direction * max(radius * 4.0, 2.0)
        else:
            sensor = cam.data.sensor_width
            half_fov = math.atan(sensor / (2.0 * cam.data.lens))
            cam.location = centre + direction * (radius / math.sin(half_fov))

    # ---------------------------------------------------------------- render
    @staticmethod
    def _set_many(target, pairs) -> None:
        for attr, val in pairs:
            if hasattr(target, attr):
                try:
                    setattr(target, attr, val)
                except (AttributeError, TypeError):
                    pass

    def _enable_gpu(self) -> str:
        """Use whatever accelerator this machine has; fall back to CPU."""
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
        except (KeyError, AttributeError):
            return "CPU"
        for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            prefs.get_devices()
            usable = [d for d in prefs.devices if d.type == backend]
            if usable:
                for d in prefs.devices:
                    d.use = (d.type == backend)
                bpy.context.scene.cycles.device = 'GPU'
                return backend
        bpy.context.scene.cycles.device = 'CPU'
        return "CPU"

    def _cycles_settings(self, samples: int) -> None:
        c = bpy.context.scene.cycles
        self._set_many(c, (
            ("samples", samples),
            ("preview_samples", max(16, samples // 8)),
            ("use_denoising", True),
            ("denoiser", 'OPENIMAGEDENOISE'),
            ("denoising_use_gpu", False),
            ("use_adaptive_sampling", True),
            ("adaptive_threshold", 0.01),
            ("max_bounces", 12),
            ("diffuse_bounces", 4),
            ("glossy_bounces", 6),
            # the car is mostly glass and chrome, so these two carry the look
            ("transmission_bounces", 12),
            ("transparent_max_bounces", 12),
            ("caustics_reflective", False),
            ("caustics_refractive", False),
            ("blur_glossy", 1.0),
            ("seed", self.build_cfg.seed),
        ))
        self._enable_gpu()

    def _eevee_settings(self, samples: int) -> None:
        eevee = bpy.context.scene.eevee
        for attr in ("taa_render_samples", "taa_samples"):
            if hasattr(eevee, attr):
                setattr(eevee, attr, samples)
        # Clamping indirect light is what stops a glossy dark surface (the
        # backlight, the black urethane) turning into salt-and-pepper noise.
        self._set_many(eevee, (
            ("use_raytracing", True),
            ("use_shadows", True),
            ("shadow_ray_count", 2),
            ("shadow_step_count", 6),
            ("clamp_surface_indirect", 8.0),
            ("use_fast_gi", False),
        ))

    def render_settings(self, resolution: tuple[int, int] | None = None,
                        samples: int | None = None,
                        engine: str | None = None) -> None:
        scn = bpy.context.scene
        r = scn.render

        engine = (engine or self.build_cfg.engine).lower()
        r.engine = 'CYCLES' if engine == "cycles" else 'BLENDER_EEVEE'
        res = resolution or self.build_cfg.resolution
        r.resolution_x, r.resolution_y = res
        r.resolution_percentage = 100
        r.image_settings.file_format = 'PNG'
        r.film_transparent = False

        n = samples if samples is not None else self.build_cfg.samples
        if engine == "cycles":
            self._cycles_settings(n)
        else:
            self._eevee_settings(n)

        scn.view_settings.view_transform = 'AgX'
        scn.view_settings.look = 'AgX - Base Contrast'
        scn.view_settings.exposure = self.build_cfg.exposure

    def build(self) -> bpy.types.Object:
        self.world()
        # A measured HDRI already contains the studio. Leaving the synthetic
        # lamps and softboxes switched on underneath one washes out exactly the
        # shaped reflections it was fetched for.
        if self.build_cfg.environment != "hdri":
            self.lights()
            self.softboxes()
        self.ground()
        cam = self.camera_rig()
        self.apply_view("hero_front_left")
        self.render_settings()
        return cam
