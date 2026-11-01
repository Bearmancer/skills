import runpy
import sys
from pathlib import Path


def run(file):
    sys.dont_write_bytecode = True
    here = Path(file).resolve()
    scripts = next(p for p in here.parents if p.name == "scripts")
    root = scripts.parent
    skip = {scripts, here.parent}
    kept = [p for p in sys.path if Path(p or ".").resolve() not in skip]
    sys.path[:] = [str(root), *kept]
    name = ".".join(here.relative_to(root).with_suffix("").parts)
    runpy.run_module(name, run_name="__main__", alter_sys=True)
    sys.exit(0)
