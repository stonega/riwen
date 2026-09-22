"""Voice lifecycle tests without a microphone, desktop, network or model."""
import sys
import io
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from voice.controller import VoiceController
from voice.local_asr import pcm16le_to_mono_float32
from voice.audio import Recorder


class Target:
    def __init__(self):
        self.allowed = True
        self.composing = False
        self.commits = []
        self.messages = []

    def voice_allowed(self): return self.allowed
    def voice_has_composition(self): return self.composing
    def voice_message(self, value): self.messages.append(value)
    def voice_commit(self, value): self.commits.append(value)
    def reset_context(self): pass


class Worker:
    def __init__(self, project, dispatch, callback):
        self.callback = callback
        self.commands = []
        self.closed = False
    def send(self, command, token): self.commands.append((command, token))
    def close(self): self.closed = True
    def emit(self, phase, **fields): self.callback(dict(state=phase, **fields))


class VoiceTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.controller = VoiceController(Path("."), lambda fn, value: fn(value), self.events.append,
                                          lambda seconds, callback: callback, lambda timer: None, Worker)
        self.target = Target()
        self.controller.prepare()
        self.worker = self.controller.worker
        self.worker.emit("ready")

    def start(self):
        self.controller.toggle(self.target)
        token = self.controller.token
        self.worker.emit("recording", id=token, message="Listening")
        return token

    def finish(self, token):
        self.controller.toggle(self.target)
        self.worker.emit("result", id=token, text="语音输入测试")
        self.worker.emit("ready")

    def test_dictation_commits_once_and_status_never_contains_transcript(self):
        token = self.start()
        self.finish(token)
        self.worker.emit("result", id=token, text="duplicate")
        self.assertEqual(self.target.commits, ["语音输入测试"])
        self.assertNotIn("语音输入测试", str(self.events))

    def test_late_result_cannot_reach_refocused_field(self):
        token = self.start()
        self.controller.finish()
        self.controller.cancel(self.target)
        self.target.allowed = False
        self.target.allowed = True
        self.worker.emit("result", id=token, text="stale")
        self.assertEqual(self.target.commits, [])

    def test_private_and_composing_fields_do_not_record(self):
        self.target.allowed = False
        self.controller.toggle(self.target)
        self.target.allowed = True
        self.target.composing = True
        self.controller.toggle(self.target)
        self.assertEqual(self.worker.commands, [])

    def test_privacy_or_new_composition_before_delivery_blocks_commit(self):
        for attribute in ("allowed", "composing"):
            self.setUp()
            token = self.start()
            setattr(self.target, attribute, attribute == "composing")
            self.worker.emit("result", id=token, text="stale")
            self.assertEqual(self.target.commits, [])

    def test_other_field_cannot_cancel_or_steal_active_job(self):
        token = self.start()
        other = Target()
        self.controller.cancel(other)
        self.controller.toggle(other)
        self.assertEqual(self.controller.token, token)
        self.finish(token)
        self.assertFalse(other.commits)

    def test_timeout_kills_worker_and_late_events_are_ignored(self):
        token = self.start()
        self.controller.finish()
        self.controller.timeout()
        self.assertTrue(self.worker.closed)
        self.worker.emit("result", id=token, text="stale")
        self.assertFalse(self.target.commits)
        self.controller.prepare()
        self.assertIsNot(self.controller.worker, self.worker)
        self.worker.emit("ready")
        self.assertFalse(self.controller.ready)

    def test_recording_failure_can_be_retried(self):
        self.start()
        self.worker.emit("error", message="Microphone unavailable")
        self.worker.emit("ready")
        self.assertIsNone(self.controller.target)
        self.controller.toggle(self.target)
        self.assertEqual(self.worker.commands[-1][0], "start")

    def test_shutdown_discards_jobs_and_closes_worker(self):
        token = self.start()
        self.controller.close()
        self.assertTrue(self.worker.closed)
        self.worker.emit("result", id=token, text="stale")
        self.assertFalse(self.target.commits)

    def test_cancel_waits_for_ack_and_hides_indicator(self):
        token = self.start()
        self.controller.finish()
        self.controller.cancel(self.target)
        self.assertEqual(self.target.messages[-1], "")
        self.worker.emit("ready")  # Prior recognition completes before cancel is read.
        self.assertFalse(self.controller.ready)
        self.worker.emit("error", id=token, message="old failure")
        self.assertEqual(self.controller.phase, "cancelling")
        self.worker.emit("ready", id=token, cancelled=True)
        self.assertTrue(self.controller.ready)
        self.controller.toggle(self.target)
        self.assertNotEqual(self.controller.token, token)

    def test_cancel_before_recording_ack_ignores_late_recording(self):
        self.controller.toggle(self.target)
        token = self.controller.token
        self.controller.cancel(self.target)
        self.worker.emit("recording", id=token, message="Listening")
        self.assertEqual(self.controller.phase, "cancelling")
        self.assertEqual(self.target.messages[-1], "")
        self.worker.emit("ready", id=token, cancelled=True)
        self.assertTrue(self.controller.ready)

    def test_empty_or_oversized_transcript_is_not_committed(self):
        for text in ("  ", "a" * 8193):
            token = self.start()
            self.worker.emit("result", id=token, text=text)
            self.worker.emit("ready")
        self.assertFalse(self.target.commits)

    def test_failed_worker_can_restart(self):
        self.start()
        self.worker.emit("closed")
        self.assertTrue(self.worker.closed)
        self.assertIsNone(self.controller.worker)
        self.controller.toggle(self.target)
        self.assertIsNot(self.controller.worker, self.worker)

    def test_pcm_conversion_and_validation(self):
        self.assertEqual(pcm16le_to_mono_float32(b"\0\0\0\x40"), [0, .5])
        for data in (b"x",):
            with self.assertRaises(RuntimeError): pcm16le_to_mono_float32(data)


class CaptureTest(unittest.TestCase):
    def capture(self, data):
        child = Mock(stdout=io.BytesIO(data))
        with patch("voice.audio.subprocess.Popen", return_value=child):
            recorder = Recorder()
            recorder.start()
            recorder.thread.join(timeout=1)
        return recorder, child

    def test_bounded_capture_finishes_with_first_minute(self):
        with patch("voice.audio.MAX_BYTES", 8):
            recorder, child = self.capture(b"\x01\x00" * 50)
            self.assertEqual(recorder.stop(), b"\x01\x00" * 4)
        child.terminate.assert_called()
        self.assertFalse(recorder.frames)

    def test_cancel_discards_pcm(self):
        recorder, _ = self.capture(b"\x01\x00" * 50)
        self.assertEqual(recorder.stop(discard=True), b"")
        self.assertFalse(recorder.frames)

    def test_empty_microphone_fails_without_a_transcript(self):
        recorder, _ = self.capture(b"")
        with self.assertRaises(RuntimeError): recorder.stop()


if __name__ == "__main__": unittest.main()
