"""Private line protocol. Audio and transcripts stay in pipes/memory, never logs."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile


def emit(**event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def migrate_model(module):
    destination = module.model_directory(module.MODEL_NAME)
    legacy = Path.home() / ".local/share/ibus-voice/models" / module.MODEL_DIRECTORY_NAME
    if destination.exists() or not all((legacy / name).is_file() and (legacy / name).stat().st_size > 0
                                      for name in module.MODEL_REQUIRED_FILES):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)

    def link_or_copy(src, dst):
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
        return dst

    with tempfile.TemporaryDirectory(prefix="reuse-", dir=destination.parent) as temporary:
        staged = Path(temporary) / destination.name
        shutil.copytree(legacy, staged, copy_function=link_or_copy)
        staged.replace(destination)


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if "--runtime-ready" not in sys.argv:
        emit(state="preparing", message="Preparing local voice runtime…")
        setup = Path(__file__).resolve().parents[2] / "scripts/prepare-voice.py"
        spec = importlib.util.spec_from_file_location("prepare_voice", setup)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        python = module.prepare()
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), "--runtime-ready"])
    from audio import Recorder
    import local_asr
    emit(state="preparing", message="Preparing Qwen3-ASR (first download about 879 MB)…")
    migrate_model(local_asr)
    local_asr.initialize_local_asr(local_asr.MODEL_NAME)
    recorder = Recorder()
    active = None
    emit(state="ready", message="Voice ready · F10 to speak")
    try:
        for line in sys.stdin:
            request = json.loads(line)
            command, token = request.get("command"), request.get("id")
            if command == "start" and active is None:
                try:
                    recorder.start()
                    active = token
                    emit(state="recording", id=token, message="Listening · F10 to finish · Esc to cancel")
                except Exception:
                    recorder.stop(discard=True)
                    emit(state="error", id=token, message="Cannot open the microphone. Check PipeWire and microphone permissions.")
                    emit(state="ready", message="Voice ready · F10 to retry")
            elif command == "stop" and token == active:
                try:
                    audio = recorder.stop()
                    emit(state="transcribing", id=token, message="Recognizing speech…")
                    text = local_asr.transcribe_pcm16le_bytes(audio, 16000, local_asr.MODEL_NAME)
                    emit(state="result", id=token, text=text)
                except Exception:
                    emit(state="error", id=token, message="Voice recognition failed. Check the microphone and try again.")
                finally:
                    audio, text = b"", ""
                    active = None
                    emit(state="ready", message="Voice ready · F10 to speak")
            elif command == "cancel":
                recorder.stop(discard=True)
                active = None
                emit(state="ready", id=token, cancelled=True, message="Voice ready · F10 to speak")
    finally:
        recorder.stop(discard=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Setup errors contain dependency/download diagnostics only, never audio.
        emit(state="error", message=f"Voice setup failed: {error}")
        sys.exit(1)
