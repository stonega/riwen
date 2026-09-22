"""Validate a built ZIP with GNOME's installer, isolated from the desktop."""
import os
from pathlib import Path
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
archive = project / "dist/riwen-badge@riwen.shell-extension.zip"
if not archive.exists():
    raise SystemExit("Build with bun run extension:package first")
with tempfile.TemporaryDirectory(prefix="riwen-zip-") as directory:
    root = Path(directory)
    (root / "cache").mkdir()
    # The GNOME installer moves its extracted directory, so cache/data must
    # share a filesystem. Neither should use the user's real directories.
    env = dict(os.environ, XDG_CACHE_HOME=str(root / "cache"),
               XDG_DATA_HOME=str(root / "data"), GSETTINGS_BACKEND="memory", GIO_USE_VFS="local")
    subprocess.run(["dbus-run-session", "--", "gnome-extensions", "install", str(archive)],
                   env=env, check=True)
    installed = root / "data/gnome-shell/extensions/riwen-badge@riwen"
    assert (installed / "app/src/riwen/server.py").exists()
    assert (installed / "schemas/gschemas.compiled").exists()
    assert not (installed / "app/runtime/bun").exists()
    assert not (installed / "app/runtime/uv").exists()
    assert (installed / "app/src/voice/worker.py").exists()
    subprocess.run(["python3", str(installed / "app/scripts/app.py"), "status"], env=env, check=True)
    print("PASS: GNOME installs the Python app and settings without bundled Bun or uv")
