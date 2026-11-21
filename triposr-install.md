# Installing TripoSR on the owner's machine

Install into a folder the owner chooses (the install folder). After the install, set the `TRIPOSR_DIR` environment variable to that folder. Do not install packages system-wide unless necessary. The owner must approve the install first.

On the author's test machine (Windows, Python 3.12, an NVIDIA RTX 3050 with 6 GB), the install is about 6.5 GB, and torch uses the CUDA 12.8 build. The steps below are written for Windows. On Linux, change the path separators and use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

1. `python -m venv .venv`
2. Source: download `https://github.com/VAST-AI-Research/TripoSR/archive/refs/heads/main.zip` and unpack it as `TripoSR-main` inside the install folder.
3. `.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu128` (on the author's test machine: torch 2.11.0+cu128). If the machine uses a different CUDA version, pick the matching PyTorch index.
4. `.venv\Scripts\python.exe -m pip install "omegaconf==2.3.0" "einops==0.8.1" "transformers>=4.46,<5" trimesh rembg onnxruntime scikit-image pillow huggingface_hub imageio`

   Verified on the author's test machine: transformers 4.57.6, trimesh 5.2.1, rembg 2.0.87, onnxruntime 1.32.0, scikit-image 0.26.0, numpy 2.5.5, pillow 13.0.0, huggingface_hub 0.36.2.
5. Download the weights into a `weights` folder inside the install folder:

   `snapshot_download('stabilityai/TripoSR', local_dir=r'<install folder>\weights', allow_patterns=['config.yaml','model.ckpt'])`

   Replace `<install folder>` with the real path. You can run this in Python with `from huggingface_hub import snapshot_download`.
6. Patch `TripoSR-main\tsr\models\isosurface.py` (keep the original as `isosurface.py.orig`) so that `torchmcubes` is not required (it needs a C++ compiler):
   - `from torchmcubes import marching_cubes` → `from skimage.measure import marching_cubes`
   - In `forward`, replace the try/except block, swap the `[2, 1, 0]` axes, and scale by the resolution with:
     ```
     verts, faces, _, _ = self.mc_func(level.detach().cpu().numpy(), 0.0)
     v_pos = torch.from_numpy(verts.copy()).float() / (self.resolution - 1.0)
     t_pos_idx = torch.from_numpy(faces[:, ::-1].astype(np.int64))
     ```
     Verified on the author's test machine: the mesh is watertight, the volume is positive (normals point outward), and Z is up.
7. Copy `scripts/path_a_local.py` into the install folder. At runtime the script reads `TRIPOSR_DIR` (it defaults to the current directory).

Background removal uses the `u2net` model (Apache-2.0), stored in the install folder's `rembg` directory. Do not use `bria-rmbg` (its license is CC BY-NC, which forbids commercial use).
