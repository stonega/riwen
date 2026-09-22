"""Bounded in-memory PCM capture through the desktop's default PipeWire source.

Adapted from ibus-voice's PCM capture boundary; PipeWire avoids a second native
Python microphone dependency. No recordings are written to disk.
"""
import subprocess
from threading import Thread

SAMPLE_RATE = 16000
MAX_SECONDS = 60
MAX_BYTES = SAMPLE_RATE * 2 * MAX_SECONDS


class Recorder:
    def __init__(self):
        self.child = None
        self.thread = None
        self.frames = bytearray()
        self.failed = False

    def start(self):
        if self.child is not None:
            raise RuntimeError("Already recording")
        self.frames = bytearray()
        self.failed = False
        self.child = subprocess.Popen(
            ["pw-record", "--rate=16000", "--channels=1", "--format=s16", "--raw", "-"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        child = self.child

        def read():
            try:
                while chunk := child.stdout.read(4096):
                    remaining = MAX_BYTES - len(self.frames)
                    self.frames.extend(chunk[:remaining])
                    if len(self.frames) == MAX_BYTES:
                        child.terminate()
                        break
            except OSError:
                self.failed = True
            finally:
                child.stdout.close()

        self.thread = Thread(target=read, daemon=True)
        self.thread.start()

    def stop(self, discard=False):
        child = self.child
        if child is None:
            return b""
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        self.thread.join(timeout=2)
        self.child = None
        data = b"" if discard else bytes(self.frames)
        self.frames.clear()
        if not discard and (self.failed or not data):
            raise RuntimeError("No microphone audio or capture failed")
        return data
