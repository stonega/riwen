"""Actual Riwen frontend + deterministic speech worker, private IBus tests only."""
import functools
import os
from pathlib import Path
import sys

project = Path(os.environ.get("RIWEN_TEST_APP", Path(__file__).resolve().parents[1]))
sys.path[:0] = [str(project / "src"), str(project / "src/ibus")]
from gi.repository import GLib
import voice.control
from voice.controller import VoiceController


class FixtureWorker:
    def __init__(self, project, dispatch, callback):
        self.dispatch, self.callback = dispatch, callback
        self.closed = False
        self.emit({"state": "ready", "message": "Voice ready"})

    def emit(self, event):
        if not self.closed:
            self.dispatch(self.callback, event)

    def send(self, command, token):
        if command == "start":
            self.emit({"state": "recording", "id": token, "message": "Listening"})
        elif command == "stop":
            self.emit({"state": "transcribing", "id": token, "message": "Recognizing"})
            def complete():
                self.emit({"state": "result", "id": token, "text": "语音输入测试"})
                self.emit({"state": "ready", "message": "Voice ready"})
                return False
            GLib.timeout_add(200, complete)
        elif command == "cancel":
            self.emit({"state": "ready", "id": token, "cancelled": True, "message": "Voice ready"})

    def close(self): self.closed = True


voice.control.VoiceController = functools.partial(VoiceController, worker_factory=FixtureWorker)
from main import main
main()
