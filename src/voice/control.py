"""Local prepare/cancel commands and transcript-free status for the extension."""
import json
import socket
from pathlib import Path

from gi.repository import GLib
from .controller import VoiceController


class VoiceControl:
    def __init__(self, project, directory, enabled):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "voice.sock"
        self.controller = None
        self.socket = None
        self.watch = None
        if not enabled:
            self.publish({"phase": "disabled", "message": "Voice input is disabled"})
            return
        def dispatch(callback, event):
            def call():
                callback(event)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(call)
        def later(seconds, callback):
            def call():
                callback()
                return GLib.SOURCE_REMOVE
            return GLib.timeout_add_seconds(seconds, call)
        self.controller = VoiceController(project, dispatch, self.publish, later, GLib.source_remove)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.path.unlink(missing_ok=True)
        self.socket.bind(str(self.path))
        self.path.chmod(0o600)
        self.socket.setblocking(False)
        self.watch = GLib.io_add_watch(self.socket.fileno(), GLib.IO_IN, self.receive)

    def publish(self, status):
        path = self.directory / "voice-status.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(status))
        temporary.chmod(0o600)
        temporary.replace(path)

    def receive(self, *_):
        try:
            command = self.socket.recv(32)
        except BlockingIOError:
            return GLib.SOURCE_CONTINUE
        if command == b"prepare":
            self.controller.prepare()
        elif command == b"cancel":
            self.controller.cancel()
        return GLib.SOURCE_CONTINUE

    def close(self):
        if self.controller:
            self.controller.close()
        if self.watch:
            GLib.source_remove(self.watch)
        if self.socket:
            self.socket.close()
            self.path.unlink(missing_ok=True)
        self.publish({"phase": "stopped", "message": "Voice is stopped"})
