"""Exercise the real app on a private IBus bus with a deterministic local model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

PROJECT = Path(__file__).resolve().parents[1]


def main():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, value):
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self.reply({"status": "ok"})
            elif self.path == "/v1/models":
                self.reply({"data": [{"id": "qwen3-1.7b"}]})
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(1)
            line = next(line for line in body["messages"][1]["content"].splitlines() if '"程式"' in line)
            time.sleep(.1)
            self.reply({"choices": [{"message": {"content": json.dumps({"best": int(line.split(".")[0])})}}]})

    app = Path(os.environ.get("RIWEN_TEST_APP", PROJECT))
    root = Path(os.environ.get("RIWEN_DATA_DIR", app / ".cache"))
    root.mkdir(parents=True, exist_ok=True)
    model = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=model.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="t-", dir=root) as profile:
            source = Path(os.environ.get("RIWEN_RIME_SOURCE") or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "ibus/rime")
            env = dict(os.environ, RIWEN_MODEL_URL=f"http://127.0.0.1:{model.server_port}/v1/chat/completions",
                       RIWEN_PROFILE=profile, RIWEN_SESSION_DIR=f"{profile}/session",
                       RIWEN_SCHEMA="rime_frost_double_pinyin_flypy", RIWEN_RIME_SOURCE=str(source))
            subprocess.run(["dbus-run-session", "--", sys.executable, str(PROJECT / "tests/ibus_integration.py"), profile, "--launcher"],
                           cwd=PROJECT, env=env, timeout=90, check=True)
            assert requests == [1], f"Expected one inference; got {len(requests)}"
            assert thread.is_alive(), "Launcher stopped an external model"
            print("PASS: Python launcher reused the external model without stopping it")
    finally:
        model.shutdown()
        model.server_close()
        thread.join()


if __name__ == "__main__":
    main()
