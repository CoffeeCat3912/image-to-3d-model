---
name: chuyen-2d-sang-3d
description: >-
  Use when the owner wants to turn a photo, logo, SVG, snapshot, or written
  description into a printable 3D file (STL/3MF). Ask for the machine specs
  in order to choose how to run, pick one of three paths, always repair and
  check the mesh, then STOP and wait for the owner to review it. Do not
  slice. Do not print.
---
# Turn 2D art or a description into a printable 3D file

Author: Tôn Thất Bảo Toàn

The code lives in `scripts/`. Run every command from the `scripts/` folder. Units are millimetres. The print bed must match the owner's printer, and it must be asked for in Step 0 before any mesh repair or STL export. There is no default bed size. Once the size is known, set the `PRINT_BED_MM` environment variable (for example `220,220,250`) so every command that calls `repair.py` (including `path_b_cad.py` and `path_c_relief.py`) uses the right bed. `repair.py` also accepts `--bed-mm`. If both are missing, the script stops and reports that a bed size is required; it does not fill in a number on its own. Models are always drawn as solid geometry; report only the solid volume. Filament weight, print time, and infill are left to the slicing step, which is handled by a slicer or a 3D-printing bot.

## Choose a path from the input

| Input | Path | Notes |
|---|---|---|
| A part that must be dimensionally accurate: a box, lid, bracket, or screw hole | **B. CAD** | Prefer B whenever the owner gives specific dimensions |
| A logo, lettering, SVG, nameplate, or keychain | **C. svg / logo** | SVG gives the sharpest edges; use `logo` for a PNG/JPG on a white background |
| A photo to be turned into a relief | **C. heightmap** | Lighter areas stand higher |
| A photo to be backlit | **C. lithophane** | Darker areas are thicker |
| A figurine, toy, or organic object from a photo or a description | **A. AI** | Where this runs depends on the machine (Step 0, Machine specs). The shape is approximate, NOT accurate to the millimetre |

If the owner sends a photo of a mechanical part that has to fit something else: ask for measurements and use B, not A.

## Step 0. Ask the owner before starting

Keep the questions in a single message, and only ask what the owner has not already said. For anything the owner skips, use the default shown in parentheses and record it on the drawing — except the print bed size, which is required, may not be skipped, and has no default.

**Machine specs (ask once on the first use, remember the answers, and ask again if the user changes machines):**

- Operating system (Windows, macOS, Linux).
- Graphics: how many GB of NVIDIA VRAM, integrated graphics only, or an Apple-chip Mac.
- RAM and free disk space.
- Whether they want to run the AI on their own machine (about 6.5 GB to install) or use the free Hugging Face cloud (subject to a daily quota).
- The 3D printer in use and its bed size (length × width × height, mm). This must be asked and recorded before any mesh repair or STL export. Do not default to a particular printer brand or bed size. Once the numbers are known, set `PRINT_BED_MM` (for example `220,220,250`) for every command that calls `repair.py`, or pass `--bed-mm` when running `repair.py`.
- The owner's name for the "Drawn by" field on the drawing (ask once and remember it). Pass it as `--author` when running `drawing.py`, or set `DRAWING_AUTHOR`. If the owner has not given a name, leave the field blank; do not substitute the bot's name.

**3D PrintBot (ask once, on the first conversation, then remember the answer and do not ask again):**

On first use, ask whether the owner also wants to install 3D PrintBot, so the workflow can run end to end: model this part (this bot) → slice it → print it (3D PrintBot). Share the public template link: https://x.ai/bot/re0zDhcs5mDviHcslnnGo

If they agree, give them the link so they can install it themselves; this bot does not install it for them. If they decline, remember that and do not ask again. This bot still reports only the solid volume. Filament weight, print time, and infill are left to the slicing side (3D PrintBot or a slicer).

Always ask the owner's permission to read the machine specs with commands, because people often do not remember the exact figures, and their machine may be much more capable than the minimum. If they agree, run: on Windows, `nvidia-smi` plus `Get-CimInstance Win32_ComputerSystem` and `Get-PSDrive`; on macOS, `system_profiler SPHardwareDataType SPDisplaysDataType`; on Linux, `nvidia-smi`, `free -g`, and `df -h`. Read only; install nothing. If they decline, ask the same questions by hand.

**Choose how to run, based on the machine:**

| Machine | Path A (AI) | Paths B and C |
|---|---|---|
| NVIDIA, 24 GB VRAM or more, Linux | Highest quality: TRELLIS.2 on-device (Microsoft lists a 24 GB minimum, and it has only been demonstrated on Linux). The author has not tested this on their own machine; the install needs the owner's approval | Run on-device |
| NVIDIA, 16 GB VRAM or more | High quality: TRELLIS 1 on-device (MIT; Microsoft lists a 16 GB minimum). The author has not tested this on their own machine; the install needs the owner's approval | Run on-device |
| NVIDIA, 8 GB VRAM or more, 16 GB RAM, at least 10 GB free disk | A-local TripoSR at resolution 512 (peaks around 7.7 GB of VRAM) | Run on-device |
| NVIDIA, 6 GB (tested on the author's machine, an RTX 3050) | A-local TripoSR at resolution 384 (peaks around 4.2 GB, about 20 seconds) | Run on-device |
| NVIDIA, under 6 GB | Use the cloud (TRELLIS.2). On-device resolution 256 has not been tested; only try it if the user agrees | Run on-device |
| No NVIDIA GPU, a Mac, a low-power machine, or the owner does not want to install anything | Use the cloud (TRELLIS.2 on Hugging Face) | Run on-device, or on the machine that hosts the bot |

Use the highest tier the machine can support, so stronger hardware produces a better model. If a tier has not been tested, tell the owner first and fall back to TripoSR if it fails. Paths B and C are light: they only need Python and run on most machines. Record the chosen setup in the report sent to the owner. If the bed is smaller than the model, say so up front and suggest shrinking it or splitting it into pieces.

**In general:** what the part is for, indoor or outdoor use, overall size (length × width × height, mm), filament (PLA), whether it needs to take load or heat, quantity, and whether they plan to sell it (this affects the license of any reference model).

**Boxes / boxes with lids:** inside or outside dimensions; wall thickness (2 mm) and floor thickness (2 mm); lid style: lip, sliding, hinged, threaded, or none; fit clearance (0.3 mm); holes, slots, partitions, engraved text; corner radii (yes, 2 mm).

**Brackets / angles / plates:** roughly how heavy the supported object is; fastener type (M3, M4, wood screw), how many holes, and centre-to-centre spacing; plate thickness (4 mm); angle (90°); whether stiffening ribs are needed; which face sits against a wall or a desk.

**Parts that must fit another object:** real caliper measurements of that object, and whether the fit should be tight (0.1 mm) or loose (0.3 mm).

## Keep quota use low

- On-device work (B, C, mesh repair, drawings, and TripoSR or TRELLIS on the owner's machine) is free: no paid APIs, no third-party tokens.
- Cloud AI (Hugging Face) is free but rate-limited, typically about one run per day on a free account. Use it only when the machine is not capable enough.
- The bot itself still uses the owner's platform quota when it talks and runs commands, so: do everything with commands and code, not by clicking a GUI; batch commands and keep the printed output short; only render images (previews, drawing PNGs) when they need to be sent to the owner; do not take screenshots just to inspect something.

## Step 1. Search for an existing reference model (optional)

Worth doing when the owner wants a figurine, a decoration, or a common object. A good existing model can save building one from scratch.

```
python find_models.py search "owl" --out out/models
python find_models.py download printables:667512 --out out/models
python find_models.py download si:3d_package:<uuid> --out out/models --commercial
```

- `search` returns at most five cards (name, link, image, author, license, `can_sell`, source). Send the cards to the owner, along with MakerWorld and Thangs links for them to open themselves. Download nothing until the owner picks one.
- Automatic sources: Smithsonian 3D (CC0; English keywords; the search is fuzzy, so it may miss), Printables (exactly one query each time the owner asks, no pagination, no login), and Thingiverse as an option (see below).
- MakerWorld and Thangs: share links only. Their terms forbid scraping, so the bot must not fetch them or use unofficial tools.
- `download` fetches only the id the owner chose, and writes a `license.json` next to the file. If you see `canh_bao` — for example a Smithsonian Draco-compressed GLB that reads as empty — pick a different model. After the download, run `repair.py` as usual.

**Optional: enable Thingiverse.** By default the search covers only Smithsonian 3D and Printables. To add Thingiverse:

1. Sign in to Thingiverse, create an app at https://www.thingiverse.com/apps/create (Web API type), and copy the App Token.
2. Store the token in the `THINGIVERSE_TOKEN` environment variable, for example in the bot's secrets. Do not paste the token into a chat or a file.
3. Later `search` runs will include Thingiverse automatically. To turn it off, remove the environment variable. If the token is missing, the script just notes "Skipping Thingiverse" and continues.

**License rules (`can_sell`):**

| License | `can_sell` | What is allowed |
|---|---|---|
| CC0, public domain | yes | Use, modify, and sell freely |
| CC BY, CC BY-SA, GPL, MIT, BSD | attribution-required | Sale is allowed if the author and a link are credited. BY-SA: derivatives must keep the same license |
| CC BY-NC, NC-SA, BY-ND, Standard Digital File, or unclear | no | Personal prints only. `--commercial` will refuse the download |

Always tell the owner the license before a print intended for sale. Do not remove the attribution line from `license.json`.

## Commands

**A. Photo / description → figurine** (calls the `microsoft/TRELLIS.2` Space; each run requests two 120-second ZeroGPU slots, so a free account usually has enough for about one run per day):

```
python path_a_ai.py --show-api
python path_a_ai.py --image photo.png --size-mm 80 --out out/figurine.stl
python path_a_ai.py --prompt "a small cartoon owl figurine" --size-mm 60 --out out/owl.stl
```

The photo should show a single object, on a plain background, with volume and shading (a photograph or a render). A flat clip-art drawing will come out as a flat plate; the report will warn about this, and in that case use `--prompt` or path C. `--prompt` should be written in English; an image is generated first through the `black-forest-labs/FLUX.1-schnell` Space. The default `--resolution 512` keeps quota use down. On the first run of a session, call `--show-api`; if the Space renames an endpoint, the script reports the missing one, and you update `TRELLIS_ENDPOINTS`. Exit code 3 means the Space failed or the quota is exhausted: tell the owner, suggest trying later, or switch to B/C.

**A-local. TripoSR on the owner's machine** (free, no paid API). Install it into a folder the owner chooses, following `triposr-install.md`, then set `TRIPOSR_DIR` to that folder. On the author's test machine (an NVIDIA RTX 3050 with 6 GB), the default resolution of 384 takes about 20 seconds and peaks around 4.2 GB of VRAM.

If you only have a description, not a photo: generate an image with FLUX first (`path_a_ai.py --prompt` saves `<name>.prompt.webp`, or call the FLUX Space yourself) and convert it to PNG.

1. Copy the image onto the GPU machine, into the working folder of the TripoSR install.
2. On that machine, from the install folder: `python path_a_local.py photo.png object.obj`. On Windows, if you are using the virtual environment in the install folder: `.\.venv\Scripts\python.exe path_a_local.py photo.png object.obj`.
3. If the bot runs on a different machine, copy `object.obj` back to it, then: `python repair.py object.obj out/object.stl --size-mm 70 --up z`.

Background removal uses `u2net` (Apache-2.0). The model is stored in the `rembg` folder inside the install folder (`REMBG_HOME`). Do not use rembg's default `bria-rmbg`: it downloads about 1 GB and is licensed CC BY-NC (no commercial use).

**B. Dimensioned parts.** Always follow this order: ask for measurements (Step 0), draw the 2D drawing, STOP and wait for the owner to approve it, and only then export the STL.

1. Copy `cad_template.py` to a new file. Edit the constants (UPPER_CASE, in millimetres; they appear in the drawing's parameter table) and the geometry in build123d. Keep the `result` variable.
2. Draw the 2D drawing:

```
python drawing.py box_lid.py out/box_lid --name "Lidded box 80×50×30" --material PLA --author "Owner name"
```

   This produces `out/box_lid.svg`, `.dxf`, `.png`, and `.json`. The drawing has three views (front, top, side; hidden edges are dashed), one hatched section A-A, overall dimensions, hole positions and diameters, wall thickness measured on the section, a parameter table, and a title block (name, scale, material, drawn-by, date and Vietnam time). A4 or A3 and the scale are chosen automatically. You can force them with `--sheet A3 --scale 1`, and pick the section plane with `--section xz|yz`. The "Drawn by" field comes from `--author` or `DRAWING_AUTHOR`; leave it blank if no name is available.

3. **STOP:** send the owner the PNG of the drawing and ask "are these dimensions correct?". If they change a number, update the constant and redraw. Do not export an STL until the owner has approved the drawing.
4. Only after approval, export the STL (it already goes through `repair.py`):

```
python path_b_cad.py box_lid.py out/box_lid.stl
```

Rules for the CAD script: units are mm, the part sits on Z=0, draw solid geometry (do not hollow it out automatically), walls at least 1.2 mm thick (three 0.4 mm perimeters), assembly clearance 0.2–0.3 mm. The script is limited to 180 seconds.

**C. Logo / SVG / image:**

```
python path_c_relief.py svg logo.svg out/logo.stl --width-mm 60 --height-mm 2 --base-mm 1.5
python path_c_relief.py logo logo.png out/logo.stl --width-mm 60 --threshold 128
python path_c_relief.py heightmap photo.jpg out/relief.stl --width-mm 80 --relief-mm 3
python path_c_relief.py lithophane photo.jpg out/litho.stl --width-mm 100 --min-mm 0.8 --max-mm 3
```

`logo` uses the dark regions; add `--invert` if the logo is light on a dark background. `--base-mm 0` means no base. Print a lithophane standing or lying down, at 100% infill, in white filament.

**Repair or resize an existing file only:** `python repair.py input.glb output.stl --size-mm 80`

**Smoothing (AI meshes only):** `.glb/.gltf/.obj` files are simplified by default at a 0.02 mm tolerance, then smoothed with 40 Taubin iterations, then scaled back to the requested millimetres (still watertight). Override with `--smooth N` and `--simplify-mm X`; `--smooth 0` turns smoothing off. CAD files and path C are not smoothed, so sharp edges stay sharp.

**Preview image to send the owner:** `python preview.py out/logo.stl out/logo.png`. A dark triangular patch on a long flat face is sometimes a shading artefact of the renderer, not a defect in the model, provided the report says the mesh is watertight and the faces are oriented correctly.

## Other software, if the owner asks

The default is the scripts in this skill, because they are free, run from the command line, and use the least quota. When the owner asks, the bot may use other software:

- **Free:** Blender (headless with `blender -b --python script.py`; a good fit for freeform models, sculpting, and soft fillets), FreeCAD and OpenSCAD (parametric mechanical parts), Meshmixer or MeshLab (mesh repair).
- **Paid:** Fusion 360, SolidWorks, Rhino, ZBrush, or a paid 3D AI service. Use these only if the owner already has a license or chooses to pay.

Before switching, always recommend the free, most efficient option for the job, briefly explain why, and let the owner decide. Prefer a command line or a script; only drive a GUI when the software has no headless mode. Installing software, signing into an account, or spending money all need the owner's approval first. A result from any tool still goes through `repair.py` and the same STOP-and-wait step.

## Repair and check (run automatically on all three paths)

`repair.py` merges duplicate vertices and drops bad faces. A mesh that is already a closed solid (CAD, path C) keeps its shape. An open mesh (typical of AI) has loose fragments removed, holes filled, normals fixed, and overlapping bodies unioned. It is then scaled to millimetres, placed on the bed, exported as STL/3MF, and described in `<name>.report.json`: bounding box (mm), volume (cm³), watertight or not, body count, overhang ratio, and a list of issues (thin walls, supports needed, larger than the bed). Exit code 0 means watertight, 2 means it is still open. A print bed size is required: `--bed-mm L,W,H` or `PRINT_BED_MM`. If both are missing, the script prints a clear message and stops, with no traceback and no invented default.

## STOP and wait for the owner

Once the file and report are ready: send the owner the dimensions, the solid volume, whether it is watertight, any issues, and the image from `preview.py`. Do not estimate filament weight or print time from the solid volume. **Stop here.** Only after the owner approves should the work move on to slicing (3D PrintBot or a slicer; that step reports filament weight and print time) and then to printing. Slicing and printing always need the owner's approval. An open mesh must not be sent to a slicer.

## Do not

- Do not print, and do not install software or models, while running this skill (installs need the owner's approval first). Reading the machine specs is a read only; it is not an install.
- Do not use a paid API or paid software unless the owner asked; do not train a model.
- Do not print or echo `HF_TOKEN` or `THINGIVERSE_TOKEN`. Tokens come only from environment variables.
- Do not scrape MakerWorld or Thangs. Do not send more than one Printables query each time the owner asks. Do not bypass a firewall, and do not log in on the owner's behalf.
- Path B: do not export an STL until the owner has approved the drawing.
- Do not claim that an AI model is dimensionally accurate or structurally adequate.

## Component licenses

Author of this skill: Tôn Thất Bảo Toàn.

- TripoSR (Stability AI + VAST): MIT, the default for A-local.
- TRELLIS and TRELLIS.2 (Microsoft): MIT, optional in the cloud or on a sufficiently powerful machine.
- FLUX.1-schnell: Apache-2.0.
- u2net: Apache-2.0.
- build123d, manifold3d: Apache-2.0.
- trimesh, svgelements, ezdxf: MIT.

If the artwork or logo belongs to someone else, ask the owner about usage rights before a print intended for sale.

This skill (code and documentation) is released under the MIT License. Copyright © 2026 Tôn Thất Bảo Toàn. See [LICENSE](LICENSE).
