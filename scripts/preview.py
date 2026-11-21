import argparse
import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw

LIGHT = np.array([0.4, -0.5, 0.8]) / np.linalg.norm([0.4, -0.5, 0.8])
BASE_RGB = np.array([30, 196, 176])


def view_matrix(azimuth_deg=-35.0, elevation_deg=30.0):
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(el - np.pi / 2), -np.sin(el - np.pi / 2)], [0, np.sin(el - np.pi / 2), np.cos(el - np.pi / 2)]])
    return rx @ rz


def render(mesh, size=640, margin=30):
    rot = view_matrix()
    verts = mesh.vertices @ rot.T
    normals = mesh.face_normals @ rot.T
    tris = verts[mesh.faces]
    facing = normals[:, 2] > 0
    tris, normals = tris[facing], normals[facing]
    lo, hi = verts[:, :2].min(axis=0), verts[:, :2].max(axis=0)
    scale = (size - 2 * margin) / max(hi - lo)
    xy = (tris[:, :, :2] - lo) * scale + margin
    xy[:, :, 1] = size - xy[:, :, 1]
    height = mesh.triangles_center[facing][:, 2]
    span = np.ptp(mesh.vertices[:, 2]) or 1.0
    tint = 0.7 + 0.3 * (height - mesh.vertices[:, 2].min()) / span
    tint[mesh.face_normals[facing][:, 2] < 0.5] = 1.0
    shade = (0.35 + 0.65 * np.clip(normals @ (LIGHT @ rot.T), 0, 1)) * tint
    colors = (BASE_RGB * shade[:, None]).astype(int)
    order = np.argsort(tris[:, :, 2].mean(axis=1))
    image = Image.new("RGB", (size, size), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    for i in order:
        draw.polygon([tuple(p) for p in xy[i]], fill=tuple(colors[i]))
    return image


def main(argv=None):
    parser = argparse.ArgumentParser(description="PNG preview image for an STL/3MF file.")
    parser.add_argument("input")
    parser.add_argument("output", help=".png")
    parser.add_argument("--size", type=int, default=640)
    args = parser.parse_args(argv)
    render(trimesh.load_mesh(args.input), args.size).save(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
