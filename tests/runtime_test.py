"""Model selection stays consistent across download, runtime and HTTP client."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("riwen_runtime", Path(__file__).resolve().parents[1] / "scripts/runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
from riwen.model import Model
from riwen.models import DEFAULT_MODEL, MODELS


class RuntimeTest(unittest.TestCase):
    def test_download_selects_pinned_model(self):
        for identifier, model in MODELS.items():
            with self.subTest(model=identifier), patch.dict(os.environ, RIWEN_MODEL=identifier):
                with patch.object(runtime.sys, "argv", ["runtime.py", "model-download"]), patch.object(runtime, "download") as download:
                    runtime.main()
                download.assert_called_once_with(model.url, runtime.DATA / "models" / model.filename, model.sha256)

    def test_model_file_alias_and_client_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "models").mkdir()
            for identifier, model in MODELS.items():
                (data / "models" / model.filename).touch()
                with self.subTest(model=identifier), patch.dict(os.environ, RIWEN_MODEL=identifier, RIWEN_MODEL_PORT="18081"):
                    child = Mock()
                    child.wait.return_value = 0
                    with patch.object(runtime, "DATA", data), patch.object(runtime.subprocess, "Popen", return_value=child) as spawn, patch.object(runtime.signal, "signal"):
                        self.assertEqual(runtime.start_model(cpu=True), 0)
                    args = spawn.call_args.args[0]
                    self.assertEqual(args[args.index("--model") + 1], str(data / "models" / model.filename))
                    self.assertEqual(args[args.index("--alias") + 1], identifier)
                    self.assertEqual(args[args.index("--n-gpu-layers") + 1], "0")
                    self.assertEqual(args[args.index("--reasoning") + 1], "off")
                    self.assertEqual(Model("http://127.0.0.1:18081/v1/chat/completions").model, identifier)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(Model("http://127.0.0.1:18081/v1/chat/completions").model, DEFAULT_MODEL)

    def test_unknown_local_model_fails_before_start(self):
        with patch.dict(os.environ, RIWEN_MODEL="unknown"), patch.object(runtime.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "Unknown local model"):
                runtime.start_model(cpu=True)
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
