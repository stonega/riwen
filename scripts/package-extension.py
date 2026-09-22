#!/usr/bin/env python3
"""Build the Python app and GNOME UI; language runtimes are system dependencies."""
import platform
from pathlib import Path
import shutil
import subprocess
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
UUID = "riwen-badge@riwen"


def build(target):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("The extension bundle currently targets Linux x86_64")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PROJECT / "gnome" / UUID, target)
    app = target / "app"
    app.mkdir()
    for name in ("src", "rime"):
        shutil.copytree(PROJECT / name, app / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (app / "scripts").mkdir()
    for name in ("app.py", "runtime.py", "prepare-voice.py"):
        shutil.copyfile(PROJECT / "scripts" / name, app / "scripts" / name)
    shutil.copyfile(PROJECT / "README.md", app / "README.md")
    shutil.copytree(PROJECT / "docs", app / "docs")
    subprocess.run(["glib-compile-schemas", "--strict", str(target / "schemas")], check=True)
    return target


def main():
    target = build(PROJECT / ".cache/extension-package" / UUID)
    output = PROJECT / "dist" / f"{UUID}.shell-extension.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(target))
    print(f"Built {output} ({output.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
