"""Private Python ASR runtime; reused by the worker and the optional setup command."""
import fcntl
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from riwen.paths import PROJECT, DATA
VENV = DATA / "voice-venv"


def run(args):
    child = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _, errors = child.communicate(timeout=300)
        if child.returncode:
            raise RuntimeError("Voice runtime setup failed: " + errors.decode(errors="replace")[-1200:])
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def prepare():
    VENV.parent.mkdir(parents=True, exist_ok=True)
    with (VENV.parent / "voice-runtime.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return prepare_locked()


def prepare_locked():
    python = VENV / "bin/python"
    stamp = VENV / "riwen-version"
    version = "sherpa-onnx==1.13.4 numpy==2.2.6"
    if python.exists() and stamp.exists() and stamp.read_text() == version:
        return python
    executable = shutil.which("uv")
    if not executable:
        raise RuntimeError("Voice setup needs the system uv package.")
    VENV.parent.mkdir(parents=True, exist_ok=True)
    if not python.exists():
        run([executable, "venv", "--python", "3.12", "--managed-python", str(VENV)])
    run([executable, "pip", "install", "--python", str(python), *version.split()])
    stamp.write_text(version)
    return python


if __name__ == "__main__":
    print(prepare())
