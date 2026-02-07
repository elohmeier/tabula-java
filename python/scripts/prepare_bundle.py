from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    package_root = _package_root()
    candidate = package_root.parent
    if (candidate / "pom.xml").exists():
        return candidate
    return package_root


def _runtime_dir() -> Path:
    package_root = _package_root()
    return package_root / "src" / "tabula_java_runtime" / "runtime"


def _platform_id() -> tuple[str, str, str]:
    sys_platform = sys.platform
    machine = platform.machine().lower()

    if sys_platform.startswith("linux"):
        os_id = "linux"
        archive_ext = "tar.gz"
    elif sys_platform == "darwin":
        os_id = "mac"
        archive_ext = "tar.gz"
    elif sys_platform in ("win32", "cygwin"):
        os_id = "windows"
        archive_ext = "zip"
    else:
        raise RuntimeError(f"Unsupported platform: {sys_platform}")

    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "aarch64"
    else:
        raise RuntimeError(f"Unsupported architecture: {machine}")

    return os_id, arch, archive_ext


def _find_tool(tool_name: str) -> str | None:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / (f"{tool_name}.exe" if os.name == "nt" else tool_name)
        if candidate.exists():
            return str(candidate)
    found = shutil.which(tool_name)
    return found


def _download_jdk_cache() -> Path:
    os_id, arch, archive_ext = _platform_id()
    cache_root = _repo_root() / ".cache" / "jdk25"
    cache_root.mkdir(parents=True, exist_ok=True)

    install_dir = cache_root / f"{os_id}-{arch}"
    if install_dir.exists():
        return install_dir

    archive_path = cache_root / f"{os_id}-{arch}.{archive_ext}"
    url = (
        "https://api.adoptium.net/v3/binary/latest/25/ga/"
        f"{os_id}/{arch}/jdk/hotspot/normal/eclipse"
    )
    print(f"Downloading JDK 25 from {url}")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "tabula-java-cibuildwheel/1.0"})
        with urllib.request.urlopen(request) as response, archive_path.open("wb") as out:
            shutil.copyfileobj(response, out)
    except Exception:
        # Fallback to urlretrieve for environments where custom request handling behaves differently.
        urllib.request.urlretrieve(url, archive_path)

    tmp_extract = cache_root / f"extract-{os_id}-{arch}"
    if tmp_extract.exists():
        shutil.rmtree(tmp_extract)
    tmp_extract.mkdir(parents=True, exist_ok=True)

    if archive_ext == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(tmp_extract)
    else:
        with tarfile.open(archive_path) as tf:
            tf.extractall(tmp_extract)

    homes = [p for p in tmp_extract.iterdir() if p.is_dir()]
    if not homes:
        raise RuntimeError("JDK archive extraction produced no directories")

    extracted_home = homes[0]
    shutil.move(str(extracted_home), str(install_dir))
    shutil.rmtree(tmp_extract, ignore_errors=True)

    return install_dir


def _resolve_tool(tool_name: str) -> str:
    found = _find_tool(tool_name)
    if found:
        return found

    jdk_home = _download_jdk_cache()
    bin_name = f"{tool_name}.exe" if os.name == "nt" else tool_name
    candidate = jdk_home / "bin" / bin_name
    if not candidate.exists():
        raise RuntimeError(f"Could not locate {tool_name} in downloaded JDK at {candidate}")
    return str(candidate)


def _copy_fat_jar(runtime_dir: Path) -> Path:
    explicit_jar = os.environ.get("TABULA_JAR_PATH")
    if explicit_jar:
        src = Path(explicit_jar)
        if not src.exists():
            raise RuntimeError(f"TABULA_JAR_PATH points to missing file: {src}")
        dst = runtime_dir / "tabula.jar"
        shutil.copy2(src, dst)
        return dst

    staged = _package_root() / "tabula.jar"
    if staged.exists():
        dst = runtime_dir / "tabula.jar"
        shutil.copy2(staged, dst)
        return dst

    target_dir = _repo_root() / "target"
    jars = sorted(target_dir.glob("tabula-*-jar-with-dependencies.jar"))
    if not jars:
        raise RuntimeError(
            "No tabula fat jar found under target/. Run: mvn --batch-mode compile assembly:single -Dmaven.test.skip=true"
        )

    src = jars[0]
    dst = runtime_dir / "tabula.jar"
    shutil.copy2(src, dst)
    return dst


def _build_runtime(jdeps: str, jlink: str, jar_path: Path, runtime_dir: Path) -> None:
    modules = subprocess.check_output(
        [jdeps, "--print-module-deps", "--ignore-missing-deps", str(jar_path)], text=True
    ).strip()

    if not modules:
        raise RuntimeError("jdeps returned no modules")

    jre_out = runtime_dir / "jre"
    subprocess.check_call(
        [
            jlink,
            "--add-modules",
            modules,
            "--strip-debug",
            "--no-man-pages",
            "--no-header-files",
            "--compress=2",
            "--output",
            str(jre_out),
        ]
    )

    # jlink places libjvm.so in lib/server, while several JRE libs link against
    # libjvm.so with RPATH=$ORIGIN (lib). Keep a copy in lib so auditwheel can
    # resolve internal dependencies when repairing Linux wheels.
    if sys.platform.startswith("linux"):
        lib_dir = jre_out / "lib"
        libjvm_server = lib_dir / "server" / "libjvm.so"
        libjvm_flat = lib_dir / "libjvm.so"
        if libjvm_server.exists() and not libjvm_flat.exists():
            shutil.copy2(libjvm_server, libjvm_flat)

        # Remove optional desktop/audio native libraries that depend on X11/ALSA
        # system libraries unavailable in manylinux images. Tabula runs headless.
        for relpath in ("lib/libawt_xawt.so", "lib/libjawt.so", "lib/libjsound.so"):
            candidate = jre_out / relpath
            if candidate.exists():
                candidate.unlink()


def main() -> int:
    package_root = _package_root()
    build_dir = package_root / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    for egg_info in (package_root / "src").glob("*.egg-info"):
        if egg_info.exists():
            shutil.rmtree(egg_info)

    runtime_dir = _runtime_dir()
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    jar_path = _copy_fat_jar(runtime_dir)
    jdeps = _resolve_tool("jdeps")
    jlink = _resolve_tool("jlink")

    print(f"Using jdeps: {jdeps}")
    print(f"Using jlink: {jlink}")
    _build_runtime(jdeps, jlink, jar_path, runtime_dir)
    print("Prepared tabula-java runtime bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
