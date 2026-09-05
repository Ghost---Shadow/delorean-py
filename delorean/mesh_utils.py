"""Mesh construction helpers.

Thin, dependency-free wrappers over bpy/bmesh so that the part modules read as
geometry description rather than API plumbing.
"""
from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

import bmesh
import bpy
from mathutils import Matrix

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

_TARGET_COLLECTION: bpy.types.Collection | None = None


# ----------------------------------------------------------------- collection
def set_target_collection(coll: bpy.types.Collection) -> None:
    """Every object built from here on is linked into `coll`."""
    global _TARGET_COLLECTION
    _TARGET_COLLECTION = coll


def link(ob: bpy.types.Object) -> bpy.types.Object:
    coll = _TARGET_COLLECTION or bpy.context.scene.collection
    coll.objects.link(ob)
    return ob


# --------------------------------------------------------------- construction
def obj_from_pydata(name: str, verts: Sequence[Vec3],
                    faces: Sequence[Sequence[int]],
                    edges: Sequence[Sequence[int]] = ()) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    me.from_pydata(list(verts), [list(e) for e in edges], [list(f) for f in faces])
    me.validate()
    me.update()
    return link(bpy.data.objects.new(name, me))


def obj_from_bmesh(name: str, bm: bmesh.types.BMesh) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return link(bpy.data.objects.new(name, me))


def loft(name: str, rings: Sequence[Sequence[Vec3]], cap_first: bool = True,
         cap_last: bool = True) -> bpy.types.Object:
    """Bridge a sequence of equal-length open profiles into a surface."""
    n = len(rings[0])
    if any(len(r) != n for r in rings):
        raise ValueError("loft: every ring must have the same point count")

    verts: list[Vec3] = []
    for ring in rings:
        verts.extend(ring)

    faces: list[tuple[int, ...]] = []
    for i in range(len(rings) - 1):
        a, b = i * n, (i + 1) * n
        for j in range(n - 1):
            faces.append((a + j, a + j + 1, b + j + 1, b + j))
    if cap_first:
        faces.append(tuple(range(n - 1, -1, -1)))
    if cap_last:
        base = (len(rings) - 1) * n
        faces.append(tuple(range(base, base + n)))
    ob = obj_from_pydata(name, verts, faces)
    recalc_normals(ob, outward=False)
    return ob


def prism(name: str, poly: Sequence[Vec2], lo: float, hi: float,
          axis: str = "Y") -> bpy.types.Object:
    """Solid prism: a 2-D polygon swept along `axis`.

    axis="Y": polygon points are (x, z), swept in y.
    axis="Z": polygon points are (x, y), swept in z.
    """
    n = len(poly)
    if axis == "Y":
        def place(p: Vec2, t: float) -> Vec3:
            return (p[0], t, p[1])
    elif axis == "Z":
        def place(p: Vec2, t: float) -> Vec3:
            return (p[0], p[1], t)
    else:
        raise ValueError("prism: unsupported axis " + repr(axis))

    verts = [place(p, lo) for p in poly] + [place(p, hi) for p in poly]
    faces: list[tuple[int, ...]] = [tuple(range(n - 1, -1, -1)),
                                    tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
    ob = obj_from_pydata(name, verts, faces)
    # The caller's polygon may be wound either way, and a prism with inward
    # normals turns a DIFFERENCE into "keep only the cutter" — which deletes
    # the car. Force outward.
    recalc_normals(ob, outward=True)
    return ob


def offset_poly(poly: Sequence[Vec2], amount: float) -> list[Vec2]:
    """Outward offset by roughly `amount`, by scaling about the centroid.

    Adequate for shut-line gaps on the roughly convex door outline; this is not
    a true Minkowski offset and should not be used on concave shapes.
    """
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    span = max(max(abs(p[0] - cx) for p in poly),
               max(abs(p[1] - cy) for p in poly))
    s = 1.0 + amount / span
    return [(cx + (p[0] - cx) * s, cy + (p[1] - cy) * s) for p in poly]


def lathe(name: str, profile: Sequence[Vec2], steps: int = 64) -> bpy.types.Object:
    """Revolve an open profile about the Y axis.

    Profile points are (radius, axial offset).
    """
    bm = bmesh.new()
    vs = [bm.verts.new((r, a, 0.0)) for (r, a) in profile]
    for p, q in zip(vs, vs[1:]):
        bm.edges.new((p, q))
    bmesh.ops.spin(bm, geom=bm.verts[:] + bm.edges[:], cent=(0, 0, 0),
                   axis=(0, 1, 0), dvec=(0, 0, 0), angle=math.tau, steps=steps,
                   use_merge=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bmesh(name, bm)


AXIS_ROT = {
    "X": lambda: Matrix.Rotation(math.radians(90), 4, 'Y'),
    "Y": lambda: Matrix.Rotation(math.radians(90), 4, 'X'),
    "Z": lambda: Matrix.Identity(4),
}


def cylinder(name: str, radius: float, depth: float,
             location: Vec3 = (0, 0, 0), axis: str = "Y",
             segments: int = 48) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius, depth=depth,
                          matrix=AXIS_ROT[axis]())
    ob = obj_from_bmesh(name, bm)
    ob.location = location
    return ob


def cone(name: str, r1: float, r2: float, depth: float,
         location: Vec3 = (0, 0, 0), axis: str = "Y",
         segments: int = 48) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=r1, radius2=r2, depth=depth,
                          matrix=AXIS_ROT[axis]())
    ob = obj_from_bmesh(name, bm)
    ob.location = location
    return ob


def box(name: str, size: Vec3, location: Vec3 = (0, 0, 0)) -> bpy.types.Object:
    sx, sy, sz = (s / 2.0 for s in size)
    verts = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
             (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = obj_from_pydata(name, verts, faces)
    recalc_normals(ob, outward=True)
    ob.location = location
    return ob


# ------------------------------------------------------------------ operations
def sync() -> None:
    """Flush pending transforms so `matrix_world` is readable.

    Blender defers evaluation, so anything that sets `location`/`rotation` and
    then reads `matrix_world` in the same pass sees a stale matrix.
    """
    bpy.context.view_layer.update()


def activate(ob: bpy.types.Object,
             also_select: Iterable[bpy.types.Object] = ()) -> None:
    bpy.ops.object.select_all(action='DESELECT')
    for o in also_select:
        o.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def apply_modifiers(ob: bpy.types.Object) -> None:
    activate(ob)
    for m in list(ob.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError:
            ob.modifiers.remove(m)


class BooleanError(RuntimeError):
    """A boolean produced a result that cannot be right."""


def _boolean_once(ob, cutter, operation, solver):
    md = ob.modifiers.new(operation.lower(), 'BOOLEAN')
    md.operation = operation
    md.object = cutter
    md.solver = solver
    activate(ob)
    bpy.ops.object.modifier_apply(modifier=md.name)
    return len(ob.data.polygons)


def _bounds(ob: bpy.types.Object) -> tuple[float, ...]:
    if not ob.data.vertices:
        return (0.0,) * 6
    xs = [v.co.x for v in ob.data.vertices]
    ys = [v.co.y for v in ob.data.vertices]
    zs = [v.co.z for v in ob.data.vertices]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _looks_wrong(before: int, after: int, operation: str, min_polys: int,
                 bounds_before=None, bounds_after=None, slack: float = 0.002) -> str:
    if after < min_polys:
        return f"left {after} polygons (was {before})"
    if operation == 'DIFFERENCE' and after < before * 0.25:
        pct = 100 * (1 - after / before)
        return f"removed {pct:.0f}% of the mesh ({before} -> {after} polygons)"
    # Neither DIFFERENCE nor INTERSECT can make a mesh bigger. If the result
    # grew, the solver merged the cutter in instead of subtracting it - which
    # is what the FLOAT fallback does when the operands barely touch.
    if bounds_before and bounds_after:
        for i in range(3):
            if bounds_after[i] < bounds_before[i] - slack:
                return (f"grew along {'XYZ'[i]} (min {bounds_before[i]:.3f} -> "
                        f"{bounds_after[i]:.3f}); the cutter was merged in, "
                        f"not applied")
            if bounds_after[i + 3] > bounds_before[i + 3] + slack:
                return (f"grew along {'XYZ'[i]} (max {bounds_before[i + 3]:.3f} "
                        f"-> {bounds_after[i + 3]:.3f}); the cutter was merged "
                        f"in, not applied")
    return ""


def boolean(ob: bpy.types.Object, cutter: bpy.types.Object,
            operation: str = 'DIFFERENCE', apply: bool = True,
            delete_cutter: bool = True, min_polys: int = 4,
            solvers: tuple[str, ...] = ('EXACT', 'FLOAT')) -> bpy.types.Object:
    """Apply a boolean, and refuse to let a silent failure through.

    Booleans fail quietly: an inverted cutter turns a DIFFERENCE into "keep
    only the cutter", and an inside-out target makes an INTERSECT return
    nothing. Both leave a valid mesh behind, so nothing downstream notices
    until the render looks wrong.

    So the result is checked, and if it is obviously wrong the mesh is rolled
    back and the next solver is tried. EXACT is correct more often; FLOAT
    copes with the near-tangent cutters that EXACT refuses (the quarter window
    lies almost flat against the sail panel, and EXACT collapses the whole
    body on it). The order is fixed, so the build stays deterministic.
    """
    if not apply:
        md = ob.modifiers.new(operation.lower(), 'BOOLEAN')
        md.operation = operation
        md.object = cutter
        md.solver = solvers[0]
        return ob

    before = len(ob.data.polygons)
    bounds_before = _bounds(ob)
    backup = ob.data.copy()
    problem = ""

    for solver in solvers:
        after = _boolean_once(ob, cutter, operation, solver)
        problem = _looks_wrong(before, after, operation, min_polys,
                               bounds_before, _bounds(ob))
        if not problem:
            bpy.data.meshes.remove(backup)
            if delete_cutter:
                bpy.data.objects.remove(cutter, do_unlink=True)
            return ob
        # roll back and try the next solver
        spoiled, ob.data = ob.data, backup.copy()
        bpy.data.meshes.remove(spoiled)

    bpy.data.meshes.remove(backup)
    if delete_cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)
    raise BooleanError(
        f"{operation} on {ob.name!r} {problem}; tried {', '.join(solvers)}. "
        f"The cutter is probably inverted, degenerate, or misses the target.")


def recalc_normals(ob: bpy.types.Object, outward: bool = True) -> float:
    """Make face winding consistent, and outward for a closed solid.

    This is not cosmetic. Blender's exact boolean solver decides what is inside
    a mesh from its winding, so a solid whose halves disagree will intersect
    correctly on one side and return nothing on the other. Returns the signed
    volume, which is positive once the mesh is a properly oriented solid.
    """
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    volume = bm.calc_volume(signed=True)
    if outward and volume < 0.0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        volume = -volume
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return volume


def is_solid(ob: bpy.types.Object) -> tuple[bool, str]:
    """True if the mesh is a closed, consistently wound, outward-facing solid."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    open_edges = sum(1 for e in bm.edges if not e.is_manifold)
    volume = bm.calc_volume(signed=True)
    bm.free()
    if open_edges:
        return False, f"{open_edges} non-manifold edges"
    if volume <= 0.0:
        return False, f"signed volume {volume:+.5f} (inside-out)"
    return True, f"closed solid, volume {volume:.5f}"


def mirror_y(ob: bpy.types.Object, merge: float = 0.001) -> bpy.types.Object:
    md = ob.modifiers.new("Mirror", 'MIRROR')
    md.use_axis = (False, True, False)
    md.use_clip = True
    md.merge_threshold = merge
    apply_modifiers(ob)
    # the mirrored half comes out with opposite winding; leaving it that way
    # silently breaks every later boolean on that side
    recalc_normals(ob)
    return ob


def solidify(ob: bpy.types.Object, thickness: float, offset: float = -1.0,
             even: bool = False, apply: bool = True) -> bpy.types.Object:
    """Give a closed surface panel thickness.

    `even` (Blender's "Even Thickness") scales the inset by 1/cos at each
    crease so corners keep their nominal thickness. On a body with creases as
    sharp as this one that overshoots badly: the inner surface self-intersects,
    and the result — while still reporting as a closed manifold — makes the
    exact boolean solver treat one half of the car as inside-out, so door cuts
    silently return nothing on that side. Leave it off.
    """
    md = ob.modifiers.new("Solidify", 'SOLIDIFY')
    md.thickness = thickness
    md.offset = offset
    md.use_even_offset = even
    if apply:
        apply_modifiers(ob)
    return ob


def bevel(ob: bpy.types.Object, width: float, segments: int = 2,
          angle_deg: float = 40.0, apply: bool = True) -> bpy.types.Object:
    md = ob.modifiers.new("Bevel", 'BEVEL')
    md.width = width
    md.segments = segments
    md.limit_method = 'ANGLE'
    md.angle_limit = math.radians(angle_deg)
    md.harden_normals = False
    if apply:
        apply_modifiers(ob)
    return ob


def shade_smooth(ob: bpy.types.Object, angle_deg: float = 32.0) -> None:
    activate(ob)
    bpy.ops.object.shade_auto_smooth(angle=math.radians(angle_deg))


def join(name: str, objects: Sequence[bpy.types.Object]) -> bpy.types.Object:
    target = objects[0]
    if len(objects) > 1:
        activate(target, objects[1:])
        bpy.ops.object.join()
    target.name = name
    return target


def duplicate(ob: bpy.types.Object, name: str) -> bpy.types.Object:
    dup = ob.copy()
    dup.data = ob.data.copy()
    dup.name = name
    return link(dup)


def set_origin(ob: bpy.types.Object, point: Vec3) -> None:
    """Move the origin to a world-space point, leaving geometry where it is."""
    ob.data.transform(Matrix.Translation((-point[0], -point[1], -point[2])))
    ob.location = point


def mirror_object_y(ob: bpy.types.Object, name: str) -> bpy.types.Object:
    """A mirrored copy across the XZ plane, with the flip baked in."""
    dup = duplicate(ob, name)
    dup.data.transform(Matrix.Diagonal((1.0, -1.0, 1.0, 1.0)))
    dup.location = (ob.location.x, -ob.location.y, ob.location.z)
    dup.data.flip_normals()
    return dup


# ------------------------------------------------------------------- materials
def set_material(ob: bpy.types.Object, mat: bpy.types.Material) -> None:
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def assign_materials(ob: bpy.types.Object,
                     materials: Sequence[bpy.types.Material],
                     chooser: Callable[[float, float, float], int],
                     world: bool = True) -> None:
    """Assign per-face material indices via `chooser(x, y, z) -> index`.

    Coordinates are world-space by default. `poly.center` is in object space,
    which is the same thing only while the origin is still at the world origin
    — move a door's origin to its hinge first and every face suddenly reads as
    being a metre lower than it is, so the whole panel comes out black.
    """
    ob.data.materials.clear()
    for m in materials:
        ob.data.materials.append(m)
    matrix = ob.matrix_world if world else None
    for poly in ob.data.polygons:
        c = matrix @ poly.center if matrix else poly.center
        poly.material_index = chooser(c.x, c.y, c.z)
