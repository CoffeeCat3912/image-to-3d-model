"""Dimensioned 2D drawing from a build123d script that defines `result`.

Exports SVG + DXF (+ PNG via headless Google Chrome). The drawing is the
step the owner reviews before an STL is exported on path B.
"""
import argparse
import os
import json
import math
import runpy
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import ezdxf
from build123d import Box, Compound, GeomType, Plane, Pos, section

SHEETS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}
SCALES = [5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05]
MARGIN = 10.0
GAP = 30.0
TITLE_W, TITLE_H = 120.0, 36.0
TABLE_W = TITLE_W
MAX_POSITION_DIMS = 3
TEXT = 3.5
ARROW = 2.5
CURVE_SAMPLES = 24
VN = ZoneInfo("Asia/Ho_Chi_Minh")

STYLE = {
    "visible": {"stroke": "#000", "width": 0.5, "dash": None, "layer": "VISIBLE", "color": 7},
    "hidden": {"stroke": "#555", "width": 0.25, "dash": "3,1.5", "layer": "HIDDEN", "color": 8},
    "section": {"stroke": "#000", "width": 0.5, "dash": None, "layer": "SECTION", "color": 7},
    "dim": {"stroke": "#0050b4", "width": 0.18, "dash": None, "layer": "DIM", "color": 5},
    "frame": {"stroke": "#000", "width": 0.35, "dash": None, "layer": "FRAME", "color": 7},
    "center": {"stroke": "#b40000", "width": 0.18, "dash": "6,1.5,1,1.5", "layer": "CENTER", "color": 1},
}

VIEWS = {
    "front": {"origin": (0, -1, 0), "up": (0, 0, 1), "title": "FRONT VIEW (from the front)"},
    "top": {"origin": (0, 0, 1), "up": (0, 1, 0), "title": "TOP VIEW (from above)"},
    "right": {"origin": (1, 0, 0), "up": (0, 0, 1), "title": "RIGHT SIDE VIEW (from the right)"},
}


class Sheet:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.items = []

    def poly(self, points, style, closed=False, fill=None):
        self.items.append(("poly", [tuple(p) for p in points], style, closed, fill))

    def line(self, a, b, style):
        self.poly([a, b], style)

    def text(self, x, y, value, size=TEXT, anchor="middle", rotate=0.0, bold=False):
        self.items.append(("text", x, y, str(value), size, anchor, rotate, bold))

    def svg(self):
        out = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}mm" height="{self.height}mm" '
            f'viewBox="0 0 {self.width} {self.height}">',
            f'<rect x="0" y="0" width="{self.width}" height="{self.height}" fill="#fff"/>',
        ]
        flip = lambda p: f"{p[0]:.3f},{self.height - p[1]:.3f}"
        for item in self.items:
            if item[0] == "poly":
                _, points, style, closed, fill = item
                s = STYLE[style]
                tag = "polygon" if closed else "polyline"
                dash = f' stroke-dasharray="{s["dash"]}"' if s["dash"] else ""
                out.append(
                    f'<{tag} points="{" ".join(flip(p) for p in points)}" fill="{fill or "none"}" '
                    f'stroke="{s["stroke"]}" stroke-width="{s["width"]}"{dash} stroke-linejoin="round"/>'
                )
            else:
                _, x, y, value, size, anchor, rotate, bold = item
                sy = self.height - y
                rot = f' transform="rotate({-rotate:.1f} {x:.3f} {sy:.3f})"' if rotate else ""
                weight = ' font-weight="bold"' if bold else ""
                value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                out.append(
                    f'<text x="{x:.3f}" y="{sy:.3f}" font-family="DejaVu Sans, Arial, sans-serif" '
                    f'font-size="{size}" text-anchor="{anchor}"{weight}{rot}>{value}</text>'
                )
        out.append("</svg>")
        return "\n".join(out)

    def dxf(self, path):
        doc = ezdxf.new("R2010", setup=True)
        for name, s in STYLE.items():
            if s["layer"] not in doc.layers:
                linetype = "DASHED" if name == "hidden" else ("CENTER" if name == "center" else "Continuous")
                doc.layers.add(s["layer"], color=s["color"], linetype=linetype)
        doc.layers.add("TEXT", color=7)
        msp = doc.modelspace()
        aligns = {"start": "BOTTOM_LEFT", "middle": "BOTTOM_CENTER", "end": "BOTTOM_RIGHT"}
        for item in self.items:
            if item[0] == "poly":
                _, points, style, closed, _ = item
                msp.add_lwpolyline(points, close=closed, dxfattribs={"layer": STYLE[style]["layer"]})
            else:
                _, x, y, value, size, anchor, rotate, _ = item
                text = msp.add_text(value, height=size * 0.8, rotation=rotate, dxfattribs={"layer": "TEXT"})
                text.set_placement((x, y), align=ezdxf.enums.TextEntityAlignment[aligns[anchor]])
        doc.saveas(path)


def load_result(model_path):
    namespace = runpy.run_path(str(model_path), run_name="__drawing__")
    if "result" not in namespace:
        sys.exit(f"{model_path} must define a variable named `result`.")
    result = namespace["result"]
    if isinstance(result, (list, tuple)):
        result = Compound(list(result))
    params = {
        key: value for key, value in namespace.items()
        if key.isupper() and isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    return result, params


def edge_points(edge):
    if edge.geom_type == GeomType.LINE:
        params = [0.0, 1.0]
    else:
        params = [i / CURVE_SAMPLES for i in range(CURVE_SAMPLES + 1)]
    return [(p.X, p.Y) for p in edge.positions(params)]


def calibrate(view):
    """Which 3D axis is horizontal or vertical in the view, and its sign."""
    probe = Pos(10, 20, 30) * Box(2, 4, 6)
    visible, _ = probe.project_to_viewport(tuple(1000 * c for c in view["origin"]), view["up"], (0, 0, 0))
    bb = Compound(list(visible)).bounding_box()
    mapping = []
    for lo, hi in ((bb.min.X, bb.max.X), (bb.min.Y, bb.max.Y)):
        centre, span = (lo + hi) / 2, hi - lo
        axis = min(range(3), key=lambda a: abs(span - (2, 4, 6)[a]))
        sign = 1 if centre * (10, 20, 30)[axis] > 0 else -1
        mapping.append((axis, sign))
    return mapping


def project(part, view, distance):
    origin = tuple(distance * c for c in view["origin"])
    visible, hidden = part.project_to_viewport(origin, view["up"], (0, 0, 0))
    return [edge_points(e) for e in visible], [edge_points(e) for e in hidden]


def bounds(polylines):
    xs = [p[0] for line in polylines for p in line]
    ys = [p[1] for line in polylines for p in line]
    return min(xs), min(ys), max(xs), max(ys)


def section_polygons(part, plane_name):
    bb = part.bounding_box()
    centre = bb.center()
    if plane_name == "xz":
        plane = Plane(origin=(0, centre.Y, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    else:
        plane = Plane(origin=(centre.X, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    cut = section(part, plane)
    faces = cut.faces()
    polygons = []
    for face in faces:
        local = plane.to_local_coords(face)
        for wire in local.wires():
            points = []
            for edge in wire.order_edges():
                pts = edge_points(edge)
                points.extend(pts if not points else pts[1:])
            polygons.append(points)
    return plane, polygons, len(faces)


def chord_lengths(polygons, axis, value):
    """Lengths of solid spans where a line x=value (axis=0) or y=value (axis=1) cuts the polygons."""
    hits = []
    other = 1 - axis
    for poly in polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a[axis] - value) * (b[axis] - value) < 0 or (a[axis] == value) != (b[axis] == value):
                if a[axis] == b[axis]:
                    continue
                t = (value - a[axis]) / (b[axis] - a[axis])
                hits.append(a[other] + t * (b[other] - a[other]))
    hits = sorted(set(round(h, 4) for h in hits))
    return [hits[i + 1] - hits[i] for i in range(0, len(hits) - 1, 2)]


def wall_thickness(polygons):
    if not polygons:
        return []
    x0, y0, x1, y1 = bounds(polygons)
    found = []
    for frac in (0.25, 0.5, 0.75):
        found += chord_lengths(polygons, 1, y0 + frac * (y1 - y0))
        found += chord_lengths(polygons, 0, x0 + frac * (x1 - x0))
    return sorted(round(v, 2) for v in found if v > 1e-3)


def find_holes(part):
    holes = {}
    for face in part.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        circles = [e for e in face.edges() if e.geom_type == GeomType.CIRCLE and e.is_closed]
        if not circles:
            continue
        centre = sum((e.arc_center for e in circles[1:]), circles[0].arc_center) / len(circles)
        axis = circles[0].normal()
        surface = face.center()
        normal = face.normal_at(surface)
        to_axis = centre - surface
        to_axis = to_axis - axis * to_axis.dot(axis)
        kind = "hole" if normal.dot(to_axis) > 0 else "boss"
        axis_name = "XYZ"[max(range(3), key=lambda i: abs(tuple(axis)[i]))]
        depth = abs((circles[-1].arc_center - circles[0].arc_center).dot(axis)) if len(circles) > 1 else None
        key = (kind, round(circles[0].radius * 2, 2), axis_name, *(round(c, 2) for c in tuple(centre)))
        holes[key] = depth
    return [
        {"loai": k[0], "duong_kinh": k[1], "truc": k[2], "tam": k[3:], "sau": None if d is None else round(d, 2)}
        for k, d in sorted(holes.items(), key=lambda kv: kv[0][3:])
    ]


def arrow(sheet, tip, direction):
    dx, dy = direction
    px, py = -dy, dx
    base = (tip[0] - dx * ARROW, tip[1] - dy * ARROW)
    sheet.poly([(base[0] + px * ARROW / 3, base[1] + py * ARROW / 3), tip,
                (base[0] - px * ARROW / 3, base[1] - py * ARROW / 3)], "dim", closed=True, fill="#0050b4")


def dim_horizontal(sheet, x1, x2, y_feature, y_dim, value):
    for x in (x1, x2):
        sheet.line((x, y_feature + (1 if y_dim > y_feature else -1)), (x, y_dim + (1.5 if y_dim > y_feature else -1.5)), "dim")
    sheet.line((x1, y_dim), (x2, y_dim), "dim")
    arrow(sheet, (x1, y_dim), (-1, 0))
    arrow(sheet, (x2, y_dim), (1, 0))
    sheet.text((x1 + x2) / 2, y_dim + 1, fmt(value))


def dim_vertical(sheet, y1, y2, x_feature, x_dim, value):
    for y in (y1, y2):
        sheet.line((x_feature + (1 if x_dim > x_feature else -1), y), (x_dim + (1.5 if x_dim > x_feature else -1.5), y), "dim")
    sheet.line((x_dim, y1), (x_dim, y2), "dim")
    arrow(sheet, (x_dim, y1), (0, -1))
    arrow(sheet, (x_dim, y2), (0, 1))
    sheet.text(x_dim - 1, (y1 + y2) / 2, fmt(value), rotate=90)


def fmt(value):
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def scale_label(scale):
    return f"{fmt(scale)}:1" if scale >= 1 else f"1:{fmt(1 / scale)}"


def place(sheet, polylines, style, scale, offset, origin):
    ox, oy = origin
    for line in polylines:
        sheet.poly([(offset[0] + (x - ox) * scale, offset[1] + (y - oy) * scale) for x, y in line], style)


def build(part, params, args):
    bb = part.bounding_box()
    size = tuple(bb.max - bb.min)
    distance = 10 * max(size) + 100
    views = {}
    for name, view in VIEWS.items():
        visible, hidden = project(part, view, distance)
        views[name] = {"visible": visible, "hidden": hidden, "box": bounds(visible + hidden), "map": calibrate(view)}
    plane_name = args.section
    if plane_name == "auto":
        candidates = {n: section_polygons(part, n) for n in ("xz", "yz")}
        plane_name = max(candidates, key=lambda n: (candidates[n][2], sum(len(p) for p in candidates[n][1])))
        _, sec_polys, _ = candidates[plane_name]
    else:
        _, sec_polys, _ = section_polygons(part, plane_name)
    views["section"] = {"visible": sec_polys, "hidden": [], "box": bounds(sec_polys) if sec_polys else (0, 0, 1, 1)}

    def extent(name):
        x0, y0, x1, y1 = views[name]["box"]
        return x1 - x0, y1 - y0

    fw, fh = extent("front")
    tw, th = extent("top")
    rw, rh = extent("right")
    sw, sh = extent("section")
    need_w = lambda s: max(fw, tw) * s + max(rw, sw) * s + 3 * GAP
    need_h = lambda s: max(fh, rh) * s + max(th, sh) * s + 3 * GAP

    sheets = [args.sheet] if args.sheet != "auto" else ["A4", "A3"]
    fits = [
        (name, scale)
        for scale in ([args.scale] if args.scale else SCALES)
        for name in sheets
        if need_w(scale) <= SHEETS[name][0] - 2 * MARGIN - TABLE_W and need_h(scale) <= SHEETS[name][1] - 2 * MARGIN
    ]
    sheet_name, s = fits[0] if fits else (sheets[-1], args.scale or SCALES[-1])
    width, height = SHEETS[sheet_name]
    sheet = Sheet(width, height)
    sheet.poly([(MARGIN / 2, MARGIN / 2), (width - MARGIN / 2, MARGIN / 2),
                (width - MARGIN / 2, height - MARGIN / 2), (MARGIN / 2, height - MARGIN / 2)], "frame", closed=True)

    pad_x = max(0.0, (width - 2 * MARGIN - TABLE_W - need_w(s)) / 2)
    pad_y = max(0.0, (height - 2 * MARGIN - need_h(s)) / 2)
    col1_x = MARGIN + GAP + pad_x
    col2_x = col1_x + max(fw, tw) * s + GAP
    row1_y = MARGIN + GAP + pad_y
    row2_y = row1_y + max(fh, rh) * s + GAP
    slots = {"front": (col1_x, row1_y), "right": (col2_x, row1_y), "top": (col1_x, row2_y), "section": (col2_x, row2_y)}
    placed = {}
    for name, (x, y) in slots.items():
        v = views[name]
        origin = v["box"][:2]
        if name == "section":
            hatch = []
            for poly in v["visible"]:
                pts = [(x + (px - origin[0]) * s, y + (py - origin[1]) * s) for px, py in poly]
                hatch.append(pts)
            for pts in hatch:
                sheet.poly(pts, "section", closed=True, fill="#cfd8e3")
        else:
            place(sheet, v["hidden"], "hidden", s, (x, y), origin)
            place(sheet, v["visible"], "visible", s, (x, y), origin)
        w, h = extent(name)
        placed[name] = (x, y, x + w * s, y + h * s, origin)

    fx0, fy0, fx1, fy1, _ = placed["front"]
    dim_horizontal(sheet, fx0, fx1, fy0, fy0 - 9, size[views["front"]["map"][0][0]])
    dim_vertical(sheet, fy0, fy1, fx0, fx0 - 9, size[views["front"]["map"][1][0]])
    tx0, ty0, tx1, ty1, _ = placed["top"]
    dim_vertical(sheet, ty0, ty1, tx0, tx0 - 9, size[views["top"]["map"][1][0]])
    rx0, ry0, rx1, ry1, _ = placed["right"]
    dim_horizontal(sheet, rx0, rx1, ry0, ry0 - 9, size[views["right"]["map"][0][0]])

    holes = find_holes(part)
    above = {name: 0 for name in placed}
    for name in ("front", "top", "right"):
        (ha, hs), (va, vs) = views[name]["map"]
        look = "XYZ"[3 - ha - va]
        x0, y0, x1, y1, origin = placed[name]
        centres = set()
        for hole in holes:
            if hole["loai"] != "hole" or hole["truc"] != look:
                continue
            cx = x0 + (hs * hole["tam"][ha] - origin[0]) * s
            cy = y0 + (vs * hole["tam"][va] - origin[1]) * s
            centres.add((round(cx, 3), round(cy, 3)))
            r = hole["duong_kinh"] / 2 * s
            sheet.line((cx - r - 1.5, cy), (cx + r + 1.5, cy), "center")
            sheet.line((cx, cy - r - 1.5), (cx, cy + r + 1.5), "center")
            sheet.line((cx + r * 0.7, cy + r * 0.7), (cx + r + 5, cy + r + 5), "dim")
            sheet.text(cx + r + 5.5, cy + r + 5.5, f"Ø{fmt(hole['duong_kinh'])}", size=2.8, anchor="start")
        for i, cx in enumerate(sorted({c[0] for c in centres})[:MAX_POSITION_DIMS]):
            dim_horizontal(sheet, x0, cx, y1, y1 + 6 + 6 * i, (cx - x0) / s)
            above[name] = 6 + 6 * i
        for i, cy in enumerate(sorted({c[1] for c in centres})[:MAX_POSITION_DIMS]):
            dim_vertical(sheet, y0, cy, x1, x1 + 6 + 6 * i, (cy - y0) / s)

    for name, (x0, y0, x1, y1, _) in placed.items():
        title = VIEWS[name]["title"] if name in VIEWS else f"SECTION A-A ({plane_name.upper()} plane through the centre)"
        sheet.text((x0 + x1) / 2, y1 + above[name] + 7, title, size=3, bold=True)

    walls = wall_thickness(sec_polys)
    sx0, sy0, sx1, sy1, _ = placed["section"]
    if walls:
        sheet.text((sx0 + sx1) / 2, sy0 - 6, f"Thinnest wall on the section: {fmt(walls[0])} mm", size=2.8)

    lines = ["PARAMETERS (mm)"]
    lines += [f"{k} = {fmt(v)}" for k, v in params.items()]
    lines += ["", "OVERALL SIZE", f"{fmt(size[0])} × {fmt(size[1])} × {fmt(size[2])}", "",
              f"HOLES / BOSSES ({len(holes)})"]
    lines += [f"{h['loai']} Ø{fmt(h['duong_kinh'])} axis {h['truc']} at ({', '.join(fmt(c) for c in h['tam'])})"
              + (f" depth {fmt(h['sau'])}" if h["sau"] else "") for h in holes[:14]]
    if len(holes) > 14:
        lines.append(f"... and {len(holes) - 14} more holes/bosses (see the JSON file)")
    if walls:
        lines += ["", "WALL THICKNESS ON SECTION", ", ".join(fmt(w) for w in sorted(set(walls))[:8])]
    table_x = width - MARGIN - TABLE_W + 4
    y = height - MARGIN - 6
    for text_line in lines:
        bold = text_line.isupper() and bool(text_line)
        sheet.text(table_x, y, text_line, size=2.6, anchor="start", bold=bold)
        y -= 4.2
    sheet.line((table_x - 4, MARGIN / 2 + TITLE_H), (table_x - 4, height - MARGIN / 2), "frame")

    now = datetime.now(VN).strftime("%d/%m/%Y %H:%M") + " (Vietnam time)"
    bx0, by0 = width - MARGIN / 2 - TITLE_W, MARGIN / 2
    sheet.poly([(bx0, by0), (bx0 + TITLE_W, by0), (bx0 + TITLE_W, by0 + TITLE_H), (bx0, by0 + TITLE_H)], "frame", closed=True)
    for row in (9, 18, 27):
        sheet.line((bx0, by0 + row), (bx0 + TITLE_W, by0 + row), "frame")
    sheet.line((bx0 + TITLE_W / 2, by0), (bx0 + TITLE_W / 2, by0 + 27), "frame")
    sheet.text(bx0 + 3, by0 + 30, args.name, size=4, anchor="start", bold=True)
    sheet.text(bx0 + 3, by0 + 21, f"Scale: {scale_label(s)}   Sheet: {sheet_name}", size=2.8, anchor="start")
    sheet.text(bx0 + TITLE_W / 2 + 3, by0 + 21, f"Material: {args.material}", size=2.8, anchor="start")
    sheet.text(bx0 + 3, by0 + 12, f"Units: mm   General tolerance: ±{fmt(args.tolerance)}", size=2.8, anchor="start")
    sheet.text(bx0 + TITLE_W / 2 + 3, by0 + 12, f"Date: {now}", size=2.8, anchor="start")
    sheet.text(bx0 + 3, by0 + 3, f"Drawn by: {args.author}".rstrip(), size=2.8, anchor="start")
    sheet.text(bx0 + TITLE_W / 2 + 3, by0 + 3, "Status: AWAITING OWNER APPROVAL", size=2.8, anchor="start", bold=True)

    summary = {
        "ten": args.name, "kho": sheet_name, "ti_le": scale_label(s), "vat_lieu": args.material,
        "nguoi_ve": args.author, "ngay": now,
        "kich_thuoc_bao_mm": [round(v, 2) for v in size], "mat_cat": plane_name,
        "do_day_mat_cat_mm": sorted(set(walls)), "lo_tru": holes, "thong_so": params,
    }
    return sheet, summary


def render_png(svg_path, png_path, width_mm, height_mm):
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        return "google-chrome/chromium not found: skipping PNG."
    px_per_mm = 6
    w, h = int(width_mm * px_per_mm), int(height_mm * px_per_mm)
    html = png_path.with_suffix(".render.html")
    html.write_text(
        f'<html><body style="margin:0;background:#fff"><img src="{svg_path.resolve().as_uri()}" '
        f'style="width:{w}px;height:{h}px;display:block"></body></html>', encoding="utf-8")
    command = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
               f"--window-size={w},{h}", f"--screenshot={png_path.resolve()}", html.resolve().as_uri()]
    done = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if done.returncode != 0 or not png_path.exists():
        return f"Chrome failed to export the PNG: {done.stderr.strip()[-300:]}"
    return None


def main():
    parser = argparse.ArgumentParser(description="Dimensioned 2D drawing (SVG, DXF, PNG) from a build123d script.")
    parser.add_argument("model", type=Path, help=".py file that defines `result`")
    parser.add_argument("out", type=Path, help="output path, with no suffix or with .svg")
    parser.add_argument("--name", help="part name in the title block")
    parser.add_argument("--author", default=None, help="name for the Drawn by field; defaults to DRAWING_AUTHOR, or blank if unset")
    parser.add_argument("--material", default="PLA")
    parser.add_argument("--tolerance", type=float, default=0.2, help="general tolerance, mm")
    parser.add_argument("--scale", type=float, help="force the scale, e.g. 1 or 0.5")
    parser.add_argument("--sheet", choices=["auto", "A4", "A3"], default="auto")
    parser.add_argument("--section", choices=["auto", "xz", "yz"], default="auto")
    parser.add_argument("--png", type=Path, help="PNG path (defaults to next to the SVG)")
    args = parser.parse_args()
    args.name = args.name or args.model.stem
    if args.author is None:
        args.author = os.environ.get("DRAWING_AUTHOR", "").strip()
    else:
        args.author = args.author.strip()

    part, params = load_result(args.model)
    sheet, summary = build(part, params, args)
    base = args.out.with_suffix("") if args.out.suffix else args.out
    base.parent.mkdir(parents=True, exist_ok=True)
    svg_path, dxf_path = base.with_suffix(".svg"), base.with_suffix(".dxf")
    svg_path.write_text(sheet.svg(), encoding="utf-8")
    sheet.dxf(str(dxf_path))
    png_path = args.png or base.with_suffix(".png")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    problem = render_png(svg_path, png_path, sheet.width, sheet.height)
    summary.update({"svg": str(svg_path), "dxf": str(dxf_path), "png": None if problem else str(png_path)})
    if problem:
        summary["canh_bao"] = problem
    base.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("STOP: send the drawing PNG to the owner to approve the dimensions before exporting an STL.")


if __name__ == "__main__":
    main()
