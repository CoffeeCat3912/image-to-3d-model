# A skill for printable 3D models

Author: Tôn Thất Bảo Toàn

This skill turns a photo, logo, SVG, snapshot, or written description into an STL or 3MF file for 3D printing. It only builds the model. Slicing, filament weight, print time, and the actual print are handled by a slicer or a 3D-printing bot, and only after the owner has approved the file.

The full instructions for the bot are in [SKILL.md](SKILL.md).

## What it does

The bot chooses one of three paths, depending on the request:

- **Path B (CAD):** boxes, lids, brackets, and other parts that must be dimensionally accurate. The bot asks for measurements, draws a 2D drawing (three views and a section, in millimetres), stops for the owner to approve it, and only then exports a 3D file.
- **Path C:** logos, raised lettering, heightmaps, and lithophanes.
- **Path A (AI):** figurines, toys, and organic shapes from a photo or a description. The result is approximate, not accurate to the millimetre.

Every file goes through a mesh-repair step: watertightness, correct face orientation, overhangs that need supports, and the solid volume in cm³. Models are always drawn as solid geometry; the bot does not estimate filament weight from the solid volume.

## What you need

- Python 3.12 or newer is recommended.
- Paths B and C, mesh repair, and 2D drawings: install `requirements-cad.txt` (lightweight; no GPU required).
- Path A on the owner's machine: an NVIDIA GPU; install TripoSR by following [triposr-install.md](triposr-install.md) (about 6.5 GB). Set the `TRIPOSR_DIR` environment variable to the install folder.
- Path A in the cloud: a free Hugging Face account (rate-limited, typically about one run per day). Optional: an `HF_TOKEN` variable.
- Optional: Chrome or Chromium to export a PNG of the 2D drawing.
- Optional: `THINGIVERSE_TOKEN` if the owner wants Thingiverse included in the search.

## How to install it

1. Copy this whole folder into the bot's skill library, or run the scripts in `scripts/` directly.
2. Create a virtual environment and install the packages:

```
python -m venv .venv
.venv/bin/pip install -r requirements-cad.txt
```

On Windows, use `.venv\Scripts\pip.exe install -r requirements-cad.txt`.

3. (Optional, when the machine has an NVIDIA GPU and the owner agrees to the install.) Install TripoSR by following `triposr-install.md`, then set `TRIPOSR_DIR`.
4. Store any tokens only in environment variables or the bot's secrets. Never paste a token into a chat or a file.

On the first use, the bot asks permission and then reads the machine specs with commands (read-only; it installs nothing). It also asks for the print bed size (required; there is no default), the owner's name for the drawing title block, and — once — whether the owner wants to install 3D PrintBot as well. A more capable machine can use a higher-quality model; tiers the author has not tested are disclosed first.

## Works with 3D PrintBot

On the first conversation, the bot asks whether the owner also wants to install 3D PrintBot, so the workflow can run end to end: model this part (this bot) → slice it → print it (3D PrintBot). Public template: https://x.ai/bot/re0zDhcs5mDviHcslnnGo

The question is asked only once. If the owner declines, the bot remembers and does not ask again. This bot still reports only the solid volume; filament weight, print time, and infill are left to the slicing side.

## What is free

- Dimensioned CAD, logos, 2D drawings, mesh repair, and on-device AI (TripoSR, or TRELLIS when the machine is powerful enough) are free: no paid APIs, no third-party tokens.
- Cloud AI on Hugging Face is also free, but it has a daily quota.
- The bot itself still uses the owner's platform quota when it talks and runs commands. To keep that low: work with commands and code, batch commands, and only render images when they need to be sent to the owner.
- If the owner asks, the bot can use Blender, FreeCAD, or OpenSCAD (free), or a paid tool the owner already licenses. It always recommends the free, most efficient option first, then lets the owner choose. It does not install software or spend money on its own.

## Limits

- An AI model is not dimensionally accurate and must not be described as structurally adequate.
- On the CAD path, no STL is exported until the 2D drawing has been approved.
- For MakerWorld and Thangs, the bot only shares search links and does not fetch the sites, because their terms forbid automated access.
- On-device TRELLIS (16 GB or 24 GB of VRAM) has not been tested on the author's machine.
- The bot does not print, and does not install software or models, without the owner's approval.
- Without a print bed size, it will not repair a mesh or export an STL.

## License

This skill (code and documentation) is released under the MIT License. Copyright © 2026 Tôn Thất Bảo Toàn. See [LICENSE](LICENSE).

Third-party components:

- TripoSR (Stability AI + VAST): MIT.
- TRELLIS and TRELLIS.2 (Microsoft): MIT.
- FLUX.1-schnell, u2net, build123d, manifold3d: Apache-2.0.
- trimesh, svgelements, ezdxf: MIT.
