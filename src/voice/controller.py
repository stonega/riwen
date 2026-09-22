"""Focus-bound voice jobs. Public methods and events run on the IBus main loop."""
import json
import subprocess
import sys
from threading import Thread


class Worker:
    def __init__(self, project, dispatch, callback):
        self.callback = callback
        self.dispatch = dispatch
        self.closing = False
        self.child = subprocess.Popen(
            [sys.executable, str(project / "src/voice/worker.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1,
        )
        Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            for line in self.child.stdout:
                if len(line) > 65536:
                    break
                event = json.loads(line)
                if not isinstance(event, dict):
                    break
                self.dispatch(self.callback, event)
        except (OSError, ValueError):
            pass
        finally:
            self.child.stdout.close()
            self.dispatch(self.callback, {"state": "closed"})

    def send(self, command, token):
        if self.closing:
            return
        try:
            self.child.stdin.write(json.dumps({"command": command, "id": token}) + "\n")
            self.child.stdin.flush()
        except (BrokenPipeError, OSError):
            self.dispatch(self.callback, {"state": "closed"})

    def close(self):
        if self.closing:
            return
        self.closing = True
        if self.child.poll() is None:
            self.child.terminate()
        def reap():
            try:
                self.child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
            self.child.stdin.close()
        Thread(target=reap, daemon=True).start()


class VoiceController:
    def __init__(self, project, dispatch, publish, later, remove_timer, worker_factory=Worker):
        self.project, self.dispatch, self.publish = project, dispatch, publish
        self.later, self.remove_timer = later, remove_timer
        self.factory = worker_factory
        self.worker = None
        self.phase = "idle"
        self.ready = False
        self.target = None
        self.serial = 0
        self.token = None
        self.timer = None
        self.cancelling = None
        self.closed = False
        self.status("idle", "Voice · F10 to prepare")

    def status(self, phase, message):
        self.phase = phase
        self.publish({"phase": phase, "message": message})
        if self.target is not None and self.target.voice_allowed():
            self.target.voice_message(message)

    def prepare(self):
        if self.closed or self.worker is not None:
            return
        self.status("preparing", "Preparing local voice input…")
        try:
            # Capture the process identity, so events from a terminated worker
            # cannot affect its replacement.
            holder = []
            worker = self.factory(self.project, self.dispatch, lambda event: self.event(holder[0], event))
            holder.append(worker)
            self.worker = worker
        except OSError:
            self.status("error", "Could not start voice input")

    def owns(self, target):
        return self.target is target

    def toggle(self, target):
        if not target.voice_allowed():
            return
        if self.target is target and self.phase == "recording":
            self.finish()
            return
        if self.worker is None:
            self.prepare()
        if not self.ready or self.target is not None:
            target.voice_message("Voice is preparing or busy. Press F10 when ready.")
            return
        if target.voice_has_composition():
            target.voice_message("Finish the current Rime composition before dictating")
            return
        self.serial += 1
        self.token, self.target, self.ready = self.serial, target, False
        target.reset_context()
        self.status("starting", "Opening microphone…")
        self.worker.send("start", self.token)
        self.timer = self.later(10, self.timeout)

    def finish(self):
        if self.token is None or self.phase != "recording":
            return
        self.clear_timer()
        self.status("transcribing", "Recognizing speech…")
        self.worker.send("stop", self.token)
        self.timer = self.later(60, self.timeout)

    def timeout(self):
        self.timer = None
        self.cancel()
        worker, self.worker = self.worker, None
        if worker:
            worker.close()
        self.clear_timer()
        self.cancelling = None
        self.ready = False
        self.status("error", "Voice recognition timed out. Press F10 to retry.")

    def clear_timer(self):
        if self.timer is not None:
            self.remove_timer(self.timer)
            self.timer = None

    def cancel(self, target=None):
        if self.closed:
            return
        if target is not None and self.target is not target:
            return
        self.clear_timer()
        owner, token = self.target, self.token
        self.target = self.token = None
        if owner is not None:
            owner.voice_message("")
        if token is not None and self.worker:
            self.cancelling = token
            self.worker.send("cancel", token)
            self.status("cancelling", "Cancelling voice input…")
        if self.cancelling is not None:
            self.timer = self.later(60, self.timeout)

    def event(self, worker, event):
        if self.closed or worker is not self.worker:
            return
        phase = event.get("state")
        if phase == "closed":
            had_error = self.phase == "error"
            self.cancel()
            self.worker = None
            worker.close()
            self.clear_timer()
            self.cancelling = None
            self.ready = False
            if not had_error:
                self.status("error", "Voice worker stopped. Press F10 to retry.")
        elif phase == "ready":
            if self.cancelling is not None:
                if not event.get("cancelled") or event.get("id") != self.cancelling:
                    return
                self.cancelling = None
            if self.target is not None:
                return
            self.clear_timer()
            self.ready = True
            if self.phase != "error":
                self.status("ready", event.get("message", "Voice ready · F10 to speak"))
        elif phase == "preparing":
            self.status("preparing", event.get("message", "Preparing voice…"))
        elif phase == "error":
            if self.cancelling is not None or (event.get("id") is not None and event.get("id") != self.token):
                return
            message = event.get("message", "Voice input failed")
            self.clear_timer()
            if self.target:
                self.target.voice_message("")
            self.target = self.token = None
            self.status("error", message)
        elif event.get("id") == self.token and self.target is not None:
            if phase == "recording":
                self.clear_timer()
                self.status(phase, event["message"])
                def finish_recording():
                    self.timer = None
                    self.finish()
                self.timer = self.later(60, finish_recording)
            elif phase == "transcribing":
                self.status(phase, event["message"])
            elif phase == "result":
                target = self.target
                text = event.get("text", "").strip()
                self.target = self.token = None
                self.clear_timer()
                target.voice_message("")
                if target.voice_allowed() and not target.voice_has_composition() and text and len(text) <= 8192:
                    target.voice_commit(text)

    def close(self):
        self.cancel()
        self.clear_timer()
        self.closed = True
        self.ready = False
        if self.worker:
            self.worker.close()
            self.worker = None
