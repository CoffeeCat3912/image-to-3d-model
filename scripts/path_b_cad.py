import argparse
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

import repair

TIMEOUT_S = 180


def export_child(script, stl_path):
    from build123d import Compound, export_stl

    namespace = runpy.run_path(script)
    if "result" not in namespace:
        raise SystemExit("The script must assign the final solid to a variable named `result`.")
    result = namespace["result"]
    if isinstance(result, (list, tuple)):
        result = Compound(list(result))
    if not export_stl(result, stl_path, tolerance=0.01, angular_tolerance=0.1):
        raise SystemExit("build123d could not export the STL.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a build123d script and export a printable file.")
    parser.add_argument("script", help=".py file based on cad_template.py, assigning `result`")
    parser.add_argument("output", help=".stl or .3mf")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        export_child(args.script, args.output)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.stl"
        try:
            subprocess.run(
                [sys.executable, __file__, args.script, str(raw), "--child"],
                check=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            raise SystemExit(f"The script ran for more than {TIMEOUT_S} seconds and was stopped.")
        except subprocess.CalledProcessError as err:
            raise SystemExit(f"The script failed (exit code {err.returncode}); see the message above and fix the code.")
        report = repair.finish(repair.load_mesh(raw), args.output, source=args.script)
    return 0 if report["watertight"] else 2


if __name__ == "__main__":
    sys.exit(main())
