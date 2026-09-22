"""Verify RPM payload and run its read-only backend without Bun, on a private bus."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
UUID = "riwen-badge@riwen"


def unpack(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    data = subprocess.check_output(["rpm2cpio", str(archive)])
    subprocess.run(["cpio", "-idmu", "--quiet"], cwd=target, input=data, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", nargs="?")
    args = parser.parse_args()
    candidates = sorted((PROJECT / "dist").glob("riwen-*.x86_64.rpm"), key=lambda path: path.stat().st_mtime)
    archive = Path(args.archive) if args.archive else candidates[-1] if candidates else None
    if archive is None:
        parser.error("Build with python3 scripts/package-rpm.py first")
    requirements = subprocess.check_output(["rpm", "-qp", "--requires", str(archive)], text=True)
    assert "bun" not in requirements.lower()
    assert "python3-pyyaml" in requirements
    assert not subprocess.check_output(["rpm", "-qp", "--scripts", str(archive)], text=True).strip()
    if not shutil.which("bwrap"):
        parser.error("The read-only RPM integration test needs bubblewrap with overlay support")
    with tempfile.TemporaryDirectory(prefix="rw-") as directory:
        root = Path(directory)
        unpack(archive, root / "package")
        app = root / "package/usr/lib64/riwen"
        extension = root / f"package/usr/share/gnome-shell/extensions/{UUID}"
        assert (app / "native/libriwen-rime.so").is_file()
        assert (extension / "schemas/gschemas.compiled").is_file()
        assert (extension / "app").readlink() == Path("/usr/lib64/riwen")
        assert not list(app.rglob("*.ts"))
        assert not (app / "runtime/bun").exists() and not (app / "runtime/uv").exists()
        assert not (app / ".cache").exists()
        # Supply the declared librime-lua dependency inside this mount namespace
        # when it is not installed on the host. Never install an RPM on the host.
        dependency = root / "dependency"
        dependency.mkdir()
        (dependency / "usr").mkdir()
        plugin = Path(json.loads((app / "rpm-layout.json").read_text())["rime_plugin"])
        if not plugin.exists():
            release = subprocess.check_output(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}.%{ARCH}", "librime"], text=True).strip()
            cached = PROJECT / ".cache/rime-native/rpms" / f"librime-lua-{release}.rpm"
            if not cached.exists():
                parser.error("Run python3 scripts/runtime.py rime-prepare to stage the matching Lua plugin")
            unpack(cached, dependency)
        # /usr is a read-only union of host libraries, declared dependency and
        # actual RPM payload. This tests the real absolute install paths.
        sandbox = ["bwrap", "--die-with-parent", "--unshare-pid", "--ro-bind", "/", "/",
                   "--overlay-src", "/usr", "--overlay-src", str(dependency / "usr"),
                   "--overlay-src", str(root / "package/usr"), "--ro-overlay", "/usr",
                   "--tmpfs", "/tmp", "--bind", str(root), str(root), "--proc", "/proc", "--dev", "/dev", "--"]
        env = dict(os.environ, PATH="/usr/bin:/bin", PYTHONDONTWRITEBYTECODE="1",
                   RIWEN_TEST_APP="/usr/lib64/riwen", RIWEN_DATA_DIR=str(root / "data"),
                   RIWEN_SESSION_DIR=str(root / "session"))
        subprocess.run([*sandbox, "sh", "-c", "! command -v bun && riwen status"], env=env, check=True)
        # The packaged entry point also works with its default XDG data paths.
        xdg_env = dict(env, XDG_DATA_HOME=str(root / "xdg-data"), XDG_RUNTIME_DIR=str(root / "run"))
        xdg_env.pop("RIWEN_DATA_DIR")
        xdg_env.pop("RIWEN_SESSION_DIR")
        check_paths = "import sys; sys.path.insert(0, '/usr/lib64/riwen/src'); from riwen.paths import DATA, SESSION; import os; from pathlib import Path; assert DATA == Path(os.environ['XDG_DATA_HOME'])/'riwen'; assert SESSION == Path(os.environ['XDG_RUNTIME_DIR'])/'riwen'"
        subprocess.run([*sandbox, "python3", "-c", check_paths], env=xdg_env, check=True)
        ui_check = root / "extension-check.js"
        ui_check.write_text("""
import GLib from 'gi://GLib';
import {RiwenService} from 'file:///usr/share/gnome-shell/extensions/riwen-badge@riwen/service.js';
const settings = {get_string: () => '', get_boolean: () => false};
const service = new RiwenService('/usr/share/gnome-shell/extensions/riwen-badge@riwen', settings);
const loop = new GLib.MainLoop(null, false);
let failure;
(async () => {
    try {
        if ((await service.command('status')).running) throw new Error('Unexpected running session');
        if (!(await service.command('schemas')).schemes.length) throw new Error('Missing Rime schemes');
    } catch (error) { failure = error; }
    finally { loop.quit(); }
})();
loop.run();
if (failure) throw failure;
""")
        subprocess.run([*sandbox, "gjs", "-m", str(ui_check)], env=env, check=True)
        subprocess.run([*sandbox, "python3", str(PROJECT / "scripts/test-launcher.py")], env=env, timeout=110, check=True)
        assert not (app / ".cache").exists()
        print("PASS: RPM includes extension and native bridge; read-only Python backend starts/restores on a private bus with no Bun")


if __name__ == "__main__":
    main()
