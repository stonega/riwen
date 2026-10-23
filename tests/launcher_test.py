"""Failure/ownership checks complement the private-bus launcher integration."""
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("riwen_app", Path(__file__).resolve().parents[1] / "scripts/app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)


class LauncherTest(unittest.TestCase):
    def test_model_health_requires_the_selected_model(self):
        endpoint = "http://127.0.0.1:18080/v1/chat/completions"
        for advertised, selected, expected in (
            ("qwen3-1.7b", app_module.DEFAULT_MODEL, False),
            (app_module.DEFAULT_MODEL, app_module.DEFAULT_MODEL, True),
            ("qwen3-1.7b", "qwen3-1.7b", True),
            ("my-local-model", "my-local-model", True),
        ):
            with self.subTest(advertised=advertised, selected=selected):
                opener = Mock()
                opener.open.side_effect = [
                    io.BytesIO(b'{"status":"ok"}'),
                    io.BytesIO(json.dumps({"data": [{"id": advertised}]}).encode()),
                ]
                with patch.object(app_module.urllib.request, "build_opener", return_value=opener):
                    self.assertEqual(app_module.model_ready(endpoint, selected), expected)

    def test_manual_source_selection_is_preserved(self):
        app = app_module.App()
        app.log = io.StringIO()
        app.previous, app.switched = "rime", True
        with patch.object(app_module, "engine", return_value="xkb:us::eng") as engine:
            app.close()
        engine.assert_called_once_with()

    def test_disconnect_clearing_the_engine_is_repaired(self):
        app = app_module.App()
        app.log = io.StringIO()
        app.previous, app.switched = "rime", True
        with patch.object(app_module, "engine", side_effect=["riwen", "rime", "", "rime"]) as engine:
            app.close()
        self.assertEqual([call.args for call in engine.call_args_list], [(), ("rime",), (), ("rime",)])

    def test_failed_start_cleans_owned_processes_but_not_external_processes(self):
        app = app_module.App()
        with tempfile.TemporaryFile() as log:
            app.log = log
            external = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
            owned = app.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
            try:
                # switched remains false, as on a partial startup failure.
                with patch.object(app_module, "engine") as engine:
                    app.close()
                engine.assert_not_called()
                self.assertIsNotNone(owned.poll())
                self.assertIsNone(external.poll())
                with self.assertRaises(ProcessLookupError):
                    os.killpg(owned.pid, 0)
            finally:
                external.terminate()
                external.wait(timeout=5)
                if owned.poll() is None:
                    os.killpg(owned.pid, signal.SIGKILL)
                    owned.wait(timeout=5)

    def test_model_health_cannot_use_remote_or_credentialed_urls(self):
        for value in ("http://example.com/v1/chat/completions", "http://user@127.0.0.1:80/x", "https://127.0.0.1/x"):
            with self.assertRaises(RuntimeError):
                app_module.local_url(value)


if __name__ == "__main__":
    unittest.main()
