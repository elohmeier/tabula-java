from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _runtime_dir() -> Path:
    return Path(__file__).resolve().parent / "runtime"


def _java_bin(runtime_dir: Path) -> Path:
    exe = "java.exe" if os.name == "nt" else "java"
    return runtime_dir / "jre" / "bin" / exe


def main() -> int:
    runtime_dir = _runtime_dir()
    jar_path = runtime_dir / "tabula.jar"
    java_path = _java_bin(runtime_dir)

    if not jar_path.exists():
        print(f"tabula-java bundle is missing: {jar_path}", file=sys.stderr)
        return 1

    if not java_path.exists():
        print(f"Bundled java runtime is missing: {java_path}", file=sys.stderr)
        return 1

    cmd = [str(java_path), "-jar", str(jar_path), *sys.argv[1:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
