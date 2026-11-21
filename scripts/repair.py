import argparse
import json
import os
import re
import sys
from pathlib import Path

import manifold3d
import numpy as np
import trimesh

MIN_WALL_MM = 0.8
OVERHANG_DEG = 45.0
KEEP_COMPONENT_RATIO = 0.02
FLAT_RATIO = 0.05
ORGANIC_SMOOTH = 40
ORGANIC_SIMPLIFY_MM = 0.02
ORGANIC_SUFFIXES = {".glb", ".gltf", ".obj"}


MISSING_BED = (
    "Print bed size is missing. Ask the owner for the bed size "
    "(length × width × height, mm), then rerun with --bed-mm L,W,H "
    "or set the PRINT_BED_MM environment variable (for example 220,220,250)."
)


def parse_bed_mm(text):
    parts = [p for p in re.split(r"[xX×*,;\s]+", text.strip()) if p]
    try:
        bed = tuple(float(p) for p in parts)
    except ValueError as err:
        raise ValueError(f"Print bed size must be three positive numbers, for example 220,220,250. Got: {text}") from err
    if len(bed) != 3 or any(v <= 0 for v in bed):
        raise ValueError(f"Print bed size must be three positive numbers, for example 220,220,250. Got: {text}")
    return bed


def resolve_bed(cli_value=None, bed=None):
    if bed is not None:
        return bed
    raw = cli_value or os.environ.get("PRINT_BED_MM")
    if not raw:
        raise SystemExit(MISSING_BED)
    try:
        return parse_bed_mm(raw)
    except ValueError as err:
        raise SystemExit(str(err)) from err


def load_mesh(path):
    return trimesh.load_mesh(str(path))


def y_up_to_z_up(mesh):
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    return mesh


def drop_specks(mesh):
    parts = mesh.split(only_watertight=False)
    if len(parts) <= 1:
        return mesh
    biggest = max(p.extents.max() for p in parts)
    kept = [p for p in parts if p.extents.max() >= biggest * KEEP_COMPONENT_RATIO]
    return trimesh.util.concatenate(kept)


def to_manifold(part):
    solid = manifold3d.Manifold(
        manifold3d.Mesh(
            vert_properties=np.asarray(part.vertices, dtype=np.float32),
            tri_verts=np.asarray(part.faces, dtype=np.uint32),
        )
    )
    if solid.status() != manifold3d.Error.NoError or solid.is_empty():
        return None
    return solid


def manifold_union(mesh):
    solids = [to_manifold(part) for part in mesh.split(only_watertight=False)]
    if not solids or any(solid is None for solid in solids):
        return mesh
    out = manifold3d.Manifold.batch_boolean(solids, manifold3d.OpType.Add).to_mesh()
    return trimesh.Trimesh(vertices=out.vert_properties[:, :3], faces=out.tri_verts)


def repair(mesh):
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if mesh.is_volume:
        return mesh
    mesh = drop_specks(mesh)
    mesh.fill_holes()
    mesh.fix_normals()
    if mesh.is_watertight:
        mesh = manifold_union(mesh)
    return mesh


def scale_to_mm(mesh, size_mm, axis):
    extents = mesh.extents
    current = extents.max() if axis == "max" else extents["xyz".index(axis)]
    if current > 0:
        mesh.apply_scale(size_mm / current)
    return mesh


def simplify_mm(mesh, tolerance):
    solid = to_manifold(mesh)
    if solid is None:
        return mesh
    out = solid.simplify(tolerance).to_mesh()
    return trimesh.Trimesh(vertices=out.vert_properties[:, :3], faces=out.tri_verts)


def smooth(mesh, iterations):
    trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=0.53, iterations=iterations)
    return mesh


def place_on_bed(mesh):
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return mesh


def overhang_share(mesh):
    normals = mesh.face_normals
    areas = mesh.area_faces
    centers_z = mesh.triangles_center[:, 2]
    on_bed = centers_z < 0.2
    steep = normals[:, 2] < -np.cos(np.radians(90.0 - OVERHANG_DEG))
    total = areas.sum()
    return float(areas[steep & ~on_bed].sum() / total) if total > 0 else 0.0


def check(mesh, bed=None, organic=False):
    bed = resolve_bed(bed=bed)
    extents = [round(float(v), 2) for v in mesh.extents]
    watertight = bool(mesh.is_watertight)
    volume_mm3 = float(mesh.volume) if watertight else None
    issues = []
    if not watertight:
        issues.append("The mesh is not watertight: use Fix model in Bambu/Prusa, or generate the part again.")
    if not mesh.is_winding_consistent:
        issues.append("Face normals are inconsistent.")
    if mesh.body_count > 1:
        issues.append(f"There are {mesh.body_count} separate bodies; check whether that is intentional.")
    if min(extents) < MIN_WALL_MM:
        issues.append(f"A dimension is thinner than {MIN_WALL_MM} mm; the printer may not be able to print it.")
    if volume_mm3 is not None and mesh.area > 0:
        mean_thickness = 2 * volume_mm3 / mesh.area
        if mean_thickness < MIN_WALL_MM * 1.5:
            issues.append(f"Average thickness is about {mean_thickness:.2f} mm; some walls may be too thin.")
    if organic and min(extents) < FLAT_RATIO * max(extents):
        issues.append("The AI produced an almost flat sheet. Use a photo or 3D render with volume and shading, or use path C for a logo or flat artwork.")
    share = overhang_share(mesh)
    if share > 0.05:
        issues.append(f"About {share:.0%} of the surface overhangs more than {OVERHANG_DEG:.0f}°; enable supports.")
    if any(e > b for e, b in zip(extents, bed)):
        issues.append(f"The model exceeds the print bed ({bed[0]:.0f}x{bed[1]:.0f}x{bed[2]:.0f} mm).")
    return {
        "bbox_mm": extents,
        "volume_cm3": round(volume_mm3 / 1000, 2) if volume_mm3 is not None else None,
        "watertight": watertight,
        "faces": int(len(mesh.faces)),
        "bodies": int(mesh.body_count),
        "overhang_share": round(share, 3),
        "issues": issues,
    }


def finish(mesh, out_path, size_mm=None, axis="max", up="z", source=None, organic=False, smooth_iterations=0, simplify_tolerance_mm=0.0, bed=None):
    bed = resolve_bed(bed=bed)
    if up == "y":
        mesh = y_up_to_z_up(mesh)
    mesh = repair(mesh)
    if size_mm:
        mesh = scale_to_mm(mesh, size_mm, axis)
        if simplify_tolerance_mm > 0 and mesh.is_watertight:
            mesh = simplify_mm(mesh, simplify_tolerance_mm)
    if smooth_iterations > 0:
        mesh = smooth(mesh, smooth_iterations)
        if size_mm:
            mesh = scale_to_mm(mesh, size_mm, axis)
    mesh = place_on_bed(mesh)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(out_path))
    report = {"file": str(out_path), "source": str(source) if source else None, **check(mesh, bed=bed, organic=organic)}
    report["next"] = "STOP. Wait for the owner to review the file and the report. Do not slice or print until the owner approves."
    out_path.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Repair a mesh, scale it to millimetres, and check that it is printable.")
    parser.add_argument("input")
    parser.add_argument("output", help=".stl or .3mf")
    parser.add_argument("--size-mm", type=float)
    parser.add_argument("--axis", choices=["max", "x", "y", "z"], default="max")
    parser.add_argument("--up", choices=["auto", "y", "z"], default="auto")
    parser.add_argument("--smooth", type=int, help=f"Taubin iterations; default {ORGANIC_SMOOTH} for .glb/.obj (AI), 0 otherwise")
    parser.add_argument("--simplify-mm", type=float, help=f"maximum simplification tolerance (mm); default {ORGANIC_SIMPLIFY_MM} when smoothing")
    parser.add_argument("--bed-mm", help="print bed L,W,H in mm, for example 220,220,250; or set PRINT_BED_MM. One of the two is required.")
    args = parser.parse_args(argv)
    suffix = Path(args.input).suffix.lower()
    up = args.up
    if up == "auto":
        up = "y" if suffix in {".glb", ".gltf"} else "z"
    iterations = args.smooth if args.smooth is not None else (ORGANIC_SMOOTH if suffix in ORGANIC_SUFFIXES else 0)
    tolerance = args.simplify_mm if args.simplify_mm is not None else (ORGANIC_SIMPLIFY_MM if iterations else 0.0)
    bed = resolve_bed(cli_value=args.bed_mm)
    report = finish(load_mesh(args.input), args.output, args.size_mm, args.axis, up, args.input, smooth_iterations=iterations, simplify_tolerance_mm=tolerance, bed=bed)
    return 0 if report["watertight"] else 2


if __name__ == "__main__":
    sys.exit(main())
