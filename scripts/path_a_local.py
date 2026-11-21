import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import rembg
import torch
from PIL import Image

TRIPOSR_DIR = Path(os.environ.get("TRIPOSR_DIR", ".")).expanduser().resolve()
REMBG_MODEL = "u2net"
os.environ.setdefault("REMBG_HOME", str(TRIPOSR_DIR / "rembg"))
sys.path.insert(0, str(TRIPOSR_DIR / "TripoSR-main"))

from tsr.system import TSR
from tsr.utils import remove_background, resize_foreground


def prepare(image_path, foreground_ratio):
    image = remove_background(Image.open(image_path), rembg.new_session(REMBG_MODEL))
    image = np.asarray(resize_foreground(image, foreground_ratio)).astype(np.float32) / 255.0
    rgb = image[:, :, :3] * image[:, :, 3:4] + (1 - image[:, :, 3:4]) * 0.5
    return Image.fromarray((rgb * 255.0).astype(np.uint8))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Image to a 3D mesh with TripoSR on a GPU machine (mesh is not repaired yet).")
    parser.add_argument("image")
    parser.add_argument("output", help=".obj or .glb")
    parser.add_argument("--mc-resolution", type=int, default=384, help="512 needs about 7.7 GB of VRAM; on a 6 GB card it spills into system RAM")
    parser.add_argument("--chunk-size", type=int, default=32768)
    parser.add_argument("--foreground-ratio", type=float, default=0.85)
    args = parser.parse_args(argv)

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    if not (TRIPOSR_DIR / "weights").exists():
        raise SystemExit(
            "The weights folder was not found. Set the TRIPOSR_DIR environment "
            "variable to the TripoSR install folder (see triposr-install.md)."
        )
    started = time.perf_counter()
    model = TSR.from_pretrained(str(TRIPOSR_DIR / "weights"), config_name="config.yaml", weight_name="model.ckpt")
    model.renderer.set_chunk_size(args.chunk_size)
    model.to(device)
    loaded = time.perf_counter()
    image = prepare(args.image, args.foreground_ratio)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out.with_name(out.stem + ".input.png"))
    with torch.no_grad():
        scene_codes = model([image], device=device)
    mesh = model.extract_mesh(scene_codes, False, resolution=args.mc_resolution)[0]
    mesh.export(str(out))
    done = time.perf_counter()
    peak = torch.cuda.max_memory_allocated() / 2**20 if device != "cpu" else None
    print(json.dumps({
        "file": str(out),
        "device": device,
        "load_s": round(loaded - started, 1),
        "infer_s": round(done - loaded, 1),
        "peak_gpu_mib": round(peak) if peak else None,
        "faces": int(len(mesh.faces)),
        "next": "Next, run repair.py on this file (usually --up z), then STOP and wait for the owner to review it.",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
