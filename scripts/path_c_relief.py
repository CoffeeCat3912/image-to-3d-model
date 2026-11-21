import argparse
import sys

import numpy as np
import trimesh
from manifold3d import CrossSection, FillRule, OpType
from PIL import Image, ImageOps
from svgelements import SVG, Close, Line, Move, Shape

import repair

CURVE_STEPS = 24


def svg_cross_section(path):
    sections = []
    for element in SVG.parse(str(path), reify=True).elements():
        if not isinstance(element, Shape) or element.fill is None or element.fill.value is None:
            continue
        contours, current = [], []
        for seg in element.segments(transformed=True):
            if isinstance(seg, Move):
                if len(current) > 2:
                    contours.append(current)
                current = [(seg.end.x, -seg.end.y)]
            elif isinstance(seg, (Close, Line)):
                current.append((seg.end.x, -seg.end.y))
            else:
                for t in np.linspace(0, 1, CURVE_STEPS)[1:]:
                    p = seg.point(t)
                    current.append((p.x, -p.y))
        if len(current) > 2:
            contours.append(current)
        if contours:
            rule = FillRule.EvenOdd if element.values.get("fill-rule") == "evenodd" else FillRule.NonZero
            sections.append(CrossSection(contours, fillrule=rule))
    if not sections:
        raise SystemExit("The SVG has no filled shapes.")
    return CrossSection.batch_boolean(sections, OpType.Add)


def raster_cross_section(path, max_px, threshold, invert):
    image = ImageOps.exif_transpose(Image.open(path)).convert("L")
    image.thumbnail((max_px, max_px))
    mask = np.asarray(image) < threshold
    if invert:
        mask = ~mask
    height = mask.shape[0]
    rects = []
    for row, line in enumerate(mask):
        padded = np.concatenate(([False], line, [False]))
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        y0, y1 = height - row - 1, height - row
        for x0, x1 in zip(edges[::2].tolist(), edges[1::2].tolist()):
            rects.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    if not rects:
        raise SystemExit("The image has no dark regions after thresholding; try --invert or a different --threshold.")
    return CrossSection(rects, fillrule=FillRule.Positive).simplify(0.5)


def extrude_relief(section, width_mm, height_mm, base_mm, margin_mm):
    x0, y0, x1, y1 = section.bounds()
    k = width_mm / (x1 - x0)
    section = section.translate((-x0, -y0)).scale((k, k))
    solid = section.extrude(height_mm)
    if base_mm > 0:
        w, h = width_mm + 2 * margin_mm, (y1 - y0) * k + 2 * margin_mm
        plate = CrossSection.square((w, h)).translate((-margin_mm, -margin_mm)).extrude(base_mm)
        solid = plate + solid.translate((0, 0, base_mm))
    mesh = solid.to_mesh()
    return trimesh.Trimesh(vertices=mesh.vert_properties[:, :3], faces=mesh.tri_verts)


def grid_solid(top, pixel_mm):
    rows, cols = top.shape
    xs = np.arange(cols) * pixel_mm
    ys = (rows - 1 - np.arange(rows)) * pixel_mm
    gx, gy = np.meshgrid(xs, ys)
    count = rows * cols
    vertices = np.vstack([
        np.column_stack([gx.ravel(), gy.ravel(), top.ravel()]),
        np.column_stack([gx.ravel(), gy.ravel(), np.zeros(count)]),
    ])
    idx = np.arange(count).reshape(rows, cols)
    v00, v01 = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel()
    v10, v11 = idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    top_faces = np.vstack([np.column_stack([v10, v11, v01]), np.column_stack([v10, v01, v00])])
    bottom_faces = top_faces[:, ::-1] + count
    ring = np.concatenate([idx[-1, :], idx[-2::-1, -1], idx[0, -2::-1], idx[1:-1, 0]])
    a, b = ring, np.roll(ring, -1)
    walls = np.vstack([np.column_stack([a + count, b + count, b]), np.column_stack([a + count, b, a])])
    return trimesh.Trimesh(vertices=vertices, faces=np.vstack([top_faces, bottom_faces, walls]), process=False)


def load_gray(path, width_mm, pixel_mm, border_px=0):
    image = ImageOps.exif_transpose(Image.open(path)).convert("L")
    cols = max(2, int(round(width_mm / pixel_mm)))
    rows = max(2, int(round(cols * image.height / image.width)))
    gray = np.asarray(image.resize((cols, rows), Image.LANCZOS), dtype=np.float64) / 255.0
    if border_px:
        gray = np.pad(gray, border_px, constant_values=0.0)
    return gray


def lithophane(path, width_mm, pixel_mm, min_mm, max_mm, border_mm):
    border_px = int(round(border_mm / pixel_mm))
    gray = load_gray(path, width_mm, pixel_mm, border_px)
    return grid_solid(min_mm + (1.0 - gray) * (max_mm - min_mm), pixel_mm)


def heightmap(path, width_mm, pixel_mm, base_mm, relief_mm, invert):
    gray = load_gray(path, width_mm, pixel_mm)
    if invert:
        gray = 1.0 - gray
    return grid_solid(base_mm + gray * relief_mm, pixel_mm)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Logo, SVG, or image to a relief, heightmap, or lithophane.")
    sub = parser.add_subparsers(dest="mode", required=True)

    def common(p, width):
        p.add_argument("input")
        p.add_argument("output", help=".stl or .3mf")
        p.add_argument("--width-mm", type=float, default=width)

    for name in ("svg", "logo"):
        p = sub.add_parser(name)
        common(p, 60.0)
        p.add_argument("--height-mm", type=float, default=2.0, help="relief height of the artwork")
        p.add_argument("--base-mm", type=float, default=1.5, help="base under the artwork; 0 means no base")
        p.add_argument("--margin-mm", type=float, default=3.0)
        if name == "logo":
            p.add_argument("--max-px", type=int, default=400)
            p.add_argument("--threshold", type=int, default=128)
            p.add_argument("--invert", action="store_true", help="use light regions instead of dark ones")

    p = sub.add_parser("heightmap")
    common(p, 80.0)
    p.add_argument("--pixel-mm", type=float, default=0.25)
    p.add_argument("--base-mm", type=float, default=1.5)
    p.add_argument("--relief-mm", type=float, default=3.0)
    p.add_argument("--invert", action="store_true", help="raise the dark regions")

    p = sub.add_parser("lithophane")
    common(p, 100.0)
    p.add_argument("--pixel-mm", type=float, default=0.2)
    p.add_argument("--min-mm", type=float, default=0.8)
    p.add_argument("--max-mm", type=float, default=3.0)
    p.add_argument("--border-mm", type=float, default=3.0)

    args = parser.parse_args(argv)
    if args.mode == "svg":
        section = svg_cross_section(args.input)
        mesh = extrude_relief(section, args.width_mm, args.height_mm, args.base_mm, args.margin_mm)
    elif args.mode == "logo":
        section = raster_cross_section(args.input, args.max_px, args.threshold, args.invert)
        mesh = extrude_relief(section, args.width_mm, args.height_mm, args.base_mm, args.margin_mm)
    elif args.mode == "heightmap":
        mesh = heightmap(args.input, args.width_mm, args.pixel_mm, args.base_mm, args.relief_mm, args.invert)
    else:
        mesh = lithophane(args.input, args.width_mm, args.pixel_mm, args.min_mm, args.max_mm, args.border_mm)
    report = repair.finish(mesh, args.output, source=args.input)
    return 0 if report["watertight"] else 2


if __name__ == "__main__":
    sys.exit(main())
