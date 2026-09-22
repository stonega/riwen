#!/usr/bin/env python3
"""Build a Fedora RPM without installing anything or changing desktop state."""
import argparse
import importlib.util
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", args.version):
        parser.error("Use a numeric dotted version")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("The current package targets Fedora x86_64")
    for tool in ("rpmbuild", "rpm", "rpm2cpio", "cpio", "g++", "glib-compile-schemas"):
        if not shutil.which(tool):
            parser.error(f"Missing build tool: {tool}")
    spec = importlib.util.spec_from_file_location("package_extension", PROJECT / "scripts/package-extension.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    staging = PROJECT / ".cache/rpm-build"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=staging) as directory:
        root = Path(directory)
        top = root / "rpmbuild"
        for name in ("BUILD", "RPMS", "SOURCES", "SPECS", "SRPMS"):
            (top / name).mkdir(parents=True)
        payload = root / f"riwen-{args.version}"
        payload.mkdir()
        extension = package.build(payload / "extension")
        shutil.move(extension / "app", payload / "app")
        source = top / "SOURCES" / f"riwen-{args.version}.tar.gz"
        with tarfile.open(source, "w:gz") as archive:
            archive.add(payload, arcname=payload.name)
        # Prefer the normal installed build dependency. A local prototype build
        # may stage exact matching Fedora headers instead of installing devel RPMs.
        include = Path("/usr/include")
        staged_headers = not (include / "rime_api.h").is_file()
        if staged_headers:
            release = subprocess.check_output(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}.%{ARCH}", "librime"], text=True).strip()
            cache = PROJECT / ".cache/rime-native/rpms"
            cache.mkdir(parents=True, exist_ok=True)
            name = f"librime-devel-{release}"
            rpm = cache / f"{name}.rpm"
            if not rpm.exists():
                subprocess.run(["dnf", "--repo=fedora", "download", "--destdir", str(cache), name], check=True)
            header_root = root / "headers"
            header_root.mkdir()
            archive = subprocess.check_output(["rpm2cpio", str(rpm)])
            subprocess.run(["cpio", "-idmu", "--quiet"], cwd=header_root, input=archive, check=True)
            include = header_root / "usr/include"
        subprocess.run(["rpmbuild", "-ba", *( ["--nodeps"] if staged_headers else []),
                        "--define", f"_topdir {top}", "--define", f"riwen_version {args.version}",
                        "--define", f"riwen_rime_include {include}", str(PROJECT / "packaging/riwen.spec")], check=True)
        output = PROJECT / "dist"
        output.mkdir(exist_ok=True)
        for path in sorted(top.rglob("*.rpm")):
            target = output / path.name
            shutil.copy2(path, target)
            print(f"Built {target}")


if __name__ == "__main__":
    main()
