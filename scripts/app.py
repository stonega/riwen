"""One-terminal Riwen session. Own only processes we launch; restore before teardown."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from riwen.paths import PROJECT, DATA as CACHE, SESSION, PACKAGED, isolated_profile
CONTROL = SESSION / "app.sock"
STATUS = SESSION / "app-status.json"


class Stopped(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def local_url(value):
    url = urllib.parse.urlsplit(value)
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or url.username
            or url.password or url.query or url.fragment):
        raise RuntimeError("Model URL must use HTTP on 127.0.0.1")
    return urllib.parse.urlunsplit((url.scheme, url.netloc, "", "", ""))


def model_ready(endpoint):
    base = local_url(endpoint)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(base + "/health", timeout=0.6) as response:
            if json.load(response).get("status") != "ok":
                return False
        with opener.open(base + "/v1/models", timeout=0.6) as response:
            return any(item.get("id") == "qwen3-1.7b" for item in json.load(response).get("data", []))
    except (OSError, ValueError):
        return False


def free_port(kind):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def engine(name=None):
    import gi
    gi.require_version("IBus", "1.0")
    from gi.repository import IBus
    IBus.init()
    bus = IBus.Bus.new()
    if not bus.is_connected():
        raise RuntimeError("Cannot connect to IBus. Run this from your GNOME desktop session.")
    # The CLI also runs setxkbmap, which is inappropriate on a private bus and
    # unnecessary for an engine switch on GNOME Wayland.
    if name and not bus.set_global_engine(name):
        raise RuntimeError(f"IBus could not select {name}")
    current = bus.get_global_engine()
    return current.get_name() if current else ""


class App:
    def __init__(self):
        self.children = []
        self.stopping = False
        self.switched = False
        self.previous = "rime"
        self.env = dict(os.environ, RIWEN_DATA_DIR=str(CACHE), PYTHONDONTWRITEBYTECODE="1")
        self.control = None
        self.log = None
        self.state = {"phase": "starting", "message": "Starting Riwen", "schema": ""}

    def report(self, phase, message):
        self.state.update(phase=phase, message=message)
        temporary = STATUS.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state))
        temporary.chmod(0o600)
        temporary.replace(STATUS)
        print(message, flush=True)

    def tick(self):
        if self.stopping:
            raise Stopped()
        try:
            connection, _ = self.control.accept()
        except socket.timeout:
            return
        with connection:
            connection.settimeout(0.2)
            try:
                command = connection.recv(16)
                if command == b"status":
                    connection.sendall(json.dumps(dict(self.state, running=True)).encode())
                elif command == b"stop":
                    raise Stopped()
            except (socket.timeout, BrokenPipeError):
                pass

    def spawn(self, args, ready=False):
        child = subprocess.Popen(args, cwd=PROJECT, env=self.env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE if ready else self.log,
                                 stderr=self.log, start_new_session=True)
        self.children.append(child)
        return child

    def run(self, *args):
        child = self.spawn(list(args))
        while child.poll() is None:
            self.tick()
        if child.returncode:
            raise RuntimeError(f"Preparation failed: {' '.join(args)}. See {SESSION / 'app.log'}")
        self.children.remove(child)

    def wait_line(self, child, marker):
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                self.tick()
                if selector.select(0):
                    line = child.stdout.readline()
                    if marker.encode() in line:
                        return
                    if not line:
                        break
        raise RuntimeError(f"A Riwen service did not start. See {SESSION / 'app.log'}")

    def prepare_model(self):
        endpoint = self.env.get("RIWEN_MODEL_URL", "http://127.0.0.1:18080/v1/chat/completions")
        if model_ready(endpoint):
            print("Using your running Qwen model.", flush=True)
            self.env["RIWEN_MODEL_URL"] = endpoint
            return
        if "RIWEN_MODEL_URL" in self.env:
            raise RuntimeError("The configured Qwen endpoint is not healthy.")
        self.report("model", "Preparing Qwen (first download: about 1.3 GB)…")
        if not (CACHE / "models/qwen3-1.7b-q4_k_m.gguf").exists():
            self.run(sys.executable, "scripts/runtime.py", "model-download")
        if not self.env.get("RIWEN_LLAMA_SERVER") and not (CACHE / "llama-vulkan/llama-b10964/llama-server").exists():
            self.run(sys.executable, "scripts/runtime.py", "runtime-download")
        # A busy or unresponsive default endpoint belongs to someone else.
        port = free_port(socket.SOCK_STREAM)
        self.env["RIWEN_MODEL_PORT"] = str(port)
        endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
        self.env["RIWEN_MODEL_URL"] = endpoint
        child = self.spawn([sys.executable, "scripts/runtime.py", "model-start", *(["--cpu"] if self.env.get("RIWEN_CPU") == "1" else [])])
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            self.tick()
            if child.poll() is not None:
                break
            if model_ready(endpoint):
                return
        raise RuntimeError(f"Qwen did not become ready. See {SESSION / 'app.log'}")

    def start(self):
        commands = ("ibus", "curl") + (() if PACKAGED else ("g++", "rpm", "dnf", "rpm2cpio", "cpio"))
        for command in commands:
            if not shutil.which(command):
                raise RuntimeError(f"Missing system tool: {command}. See docs/implementation/setup.md")
        self.previous = engine()
        print(f"Previous input method: {self.previous or '(none)'}", file=self.log, flush=True)
        if self.previous == "riwen":
            raise RuntimeError("Riwen is already selected. Stop that session before starting another.")
        self.report("preparing", "Preparing your Rime input method…")
        self.env["RIWEN_PORT"] = str(free_port(socket.SOCK_DGRAM))
        profile = isolated_profile(self.env.get("RIWEN_PROFILE", CACHE / "app-profile"))
        self.env["RIWEN_PROFILE"] = str(profile)
        self.env.setdefault("RIWEN_VOICE", "1")
        self.env["RIWEN_VOICE_CONTROL_DIR"] = str(SESSION)
        self.run(sys.executable, "scripts/runtime.py", "rime-prepare")
        self.run(sys.executable, "scripts/runtime.py", "ibus-prepare")
        self.state["schema"] = json.loads((profile / "riwen-profile.json").read_text())["name"]
        self.prepare_model()
        bridge = self.spawn([sys.executable, "scripts/runtime.py", "bridge"], ready=True)
        self.wait_line(bridge, "Riwen listening")
        frontend = self.spawn([sys.executable, "src/ibus/main.py", "--profile", str(profile)], ready=True)
        self.wait_line(frontend, "Riwen engine registered")
        self.switched = True  # Restore even if switching partially succeeds.
        engine("riwen")
        if engine() != "riwen":
            raise RuntimeError("IBus did not select Riwen.")
        self.report("ready", "Riwen is ready. Type normally; Ctrl+C or riwen stop restores your input method.")
        while True:
            self.tick()
            if any(child.poll() is not None for child in self.children):
                raise RuntimeError(f"A Riwen service stopped. See {SESSION / 'app.log'}")

    def close(self):
        restore = False
        if self.switched:
            try:
                # Respect a manual source change made while Riwen was running.
                current = engine()
                print(f"Restoring input method: current={current}, previous={self.previous}", file=self.log, flush=True)
                if current in ("", "riwen"):
                    restore = True
                    engine(self.previous or "rime")
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                print(f"Could not restore the input method: {error}. Run: ibus engine rime", file=sys.stderr)
        for child in reversed(self.children):
            # Groups include descendants such as llama-server and download tools.
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            if child.stdout:
                child.stdout.close()
        if restore:
            try:
                # IBus can clear its global engine while unregistering a
                # transient component. Confirm restoration after disconnect too.
                if engine() in ("", "riwen"):
                    engine(self.previous or "rime")
            except RuntimeError as error:
                print(f"Could not restore the input method: {error}. Run: ibus engine rime", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Start Riwen in one terminal; stop restores the previous input method.")
    parser.add_argument("command", choices=("start", "stop", "status", "schemas", "voice-status", "voice-prepare", "voice-cancel"), nargs="?", default="start")
    args = parser.parse_args()
    if args.command.startswith("voice-"):
        if args.command == "voice-status":
            try:
                status = json.loads((SESSION / "voice-status.json").read_text())
            except (OSError, ValueError):
                status = {"phase": "stopped", "message": "Start Riwen to use voice input"}
        else:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                    client.sendto(args.command.removeprefix("voice-").encode(), str(SESSION / "voice.sock"))
                status = {"ok": True}
            except OSError:
                status = {"ok": False, "message": "Start Riwen and enable voice input first"}
        print(json.dumps(status))
        return 0
    if args.command == "schemas":
        return subprocess.call([sys.executable, str(PROJECT / "scripts/runtime.py"), "schemas"], cwd=PROJECT)
    if args.command == "status":
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(2)
                client.connect(str(CONTROL))
                client.sendall(b"status")
                print(client.recv(8192).decode())
        except (OSError, ValueError):
            state = {"phase": "stopped", "message": "Riwen is stopped"}
            running = False
            try:
                with (SESSION / "app.lock").open("r") as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        running = True
            except FileNotFoundError:
                pass
            try:
                saved = json.loads(STATUS.read_text())
                if running or saved.get("phase") == "error":
                    state = saved
            except (OSError, ValueError):
                pass
            print(json.dumps(dict(state, running=running)))
        return 0
    if args.command == "stop":
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(2)
                client.connect(str(CONTROL))
                client.sendall(b"stop")
            print("Riwen is stopping.")
        except (FileNotFoundError, ConnectionRefusedError):
            print("Riwen is not running.")
        return 0
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    SESSION.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (SESSION / "app.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Riwen is already running. Use riwen stop to stop it.", file=sys.stderr)
            return 1
        app = App()
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda *_: setattr(app, "stopping", True))
        with socket.socket(socket.AF_UNIX) as control, (SESSION / "app.log").open("w") as log:
            CONTROL.unlink(missing_ok=True)
            control.bind(str(CONTROL))
            CONTROL.chmod(0o600)
            control.listen(1)
            control.settimeout(0.1)
            app.control, app.log = control, log
            try:
                app.report("starting", "Starting Riwen…")
                app.start()
            except Stopped:
                app.report("stopping", "Restoring your input method…")
                pass
            except Exception as error:
                app.report("error", str(error))
                print(f"Riwen: {error}", file=sys.stderr)
                return 1
            finally:
                app.close()
                CONTROL.unlink(missing_ok=True)
                if app.state["phase"] != "error":
                    app.report("stopped", "Riwen is stopped")
        print("Riwen stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
