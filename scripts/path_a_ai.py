import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import httpx
from gradio_client import Client, handle_file

import repair

TRELLIS_SPACE = "microsoft/TRELLIS.2"
T2I_SPACE = "black-forest-labs/FLUX.1-schnell"
T2I_SUFFIX = ", single object, full view, centered, plain white background, no text"
TRELLIS_ENDPOINTS = ("/preprocess_image", "/image_to_3d", "/extract_glb")
SAMPLER_DEFAULTS = (7.5, 0.7, 12, 5.0, 7.5, 0.5, 12, 3.0, 1.0, 0.0, 12, 3.0)
QUOTA_HINT = (
    "The Space failed or the ZeroGPU quota is exhausted. Each run requests "
    "two 120-second GPU slots; a free account is usually enough for about "
    "one run per day. Try again later, or use path B/C if the part must be dimensionally accurate."
)


NETWORK_RETRIES = 3


def with_retry(fn, *args):
    for attempt in range(NETWORK_RETRIES):
        try:
            return fn(*args)
        except httpx.TransportError:
            if attempt == NETWORK_RETRIES - 1:
                raise
            time.sleep(5 * (attempt + 1))


def connect(space):
    return Client(space, token=os.environ.get("HF_TOKEN") or None, verbose=False)


def endpoints(client):
    return set(client.view_api(print_info=False, return_format="dict")["named_endpoints"])


def text_to_image(prompt, seed):
    client = connect(T2I_SPACE)
    image, _ = client.predict(prompt + T2I_SUFFIX, seed, False, 1024, 1024, 4, api_name="/infer")
    return image


def save_prompt_image(image, out):
    return shutil.copy(image, out.with_name(out.stem + ".prompt" + Path(image).suffix))


def image_to_glb(image_path, resolution, seed, decimation, texture):
    client = connect(TRELLIS_SPACE)
    missing = [name for name in TRELLIS_ENDPOINTS if name not in endpoints(client)]
    if missing:
        raise SystemExit(f"The Space API has changed; missing {missing}. Rerun with --show-api and update TRELLIS_ENDPOINTS.")
    prepared = client.predict(handle_file(image_path), api_name="/preprocess_image")
    client.predict(handle_file(prepared), seed, resolution, *SAMPLER_DEFAULTS, api_name="/image_to_3d")
    glb, _ = client.predict(decimation, texture, api_name="/extract_glb")
    return glb


def main(argv=None):
    parser = argparse.ArgumentParser(description="Image or text prompt to an organic 3D model via TRELLIS.2.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image")
    source.add_argument("--prompt", help="English description; an image is generated first")
    source.add_argument("--show-api", action="store_true", help="print the Space API and exit")
    parser.add_argument("--out", default="out/model.stl", help=".stl or .3mf")
    parser.add_argument("--size-mm", type=float, default=80.0, help="longest dimension after scaling")
    parser.add_argument("--resolution", choices=["512", "1024", "1536"], default="512")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--decimation", type=int, default=200000)
    parser.add_argument("--texture", type=int, default=1024)
    args = parser.parse_args(argv)

    if args.show_api:
        connect(TRELLIS_SPACE).view_api()
        return 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        image = args.image or save_prompt_image(with_retry(text_to_image, args.prompt, args.seed), out)
        glb = with_retry(image_to_glb, image, args.resolution, args.seed, args.decimation, args.texture)
    except Exception as err:
        print(json.dumps({"error": f"{type(err).__name__}: {str(err)[:300]}", "hint": QUOTA_HINT}, ensure_ascii=False))
        return 3
    raw = shutil.copy(glb, out.with_suffix(".raw.glb"))
    report = repair.finish(repair.load_mesh(raw), out, args.size_mm, "max", "y", args.image or args.prompt, organic=True, smooth_iterations=repair.ORGANIC_SMOOTH, simplify_tolerance_mm=repair.ORGANIC_SIMPLIFY_MM)
    return 0 if report["watertight"] else 2


if __name__ == "__main__":
    sys.exit(main())
