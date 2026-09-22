"""Register an experimental engine for this IBus connection; never switch engines."""
import argparse
import signal
import os
import sys
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, GLibUnix, IBus  # noqa: E402
from engine import RiwenEngine  # noqa: E402
from native import NativeRime  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice.control import VoiceControl  # noqa: E402
from riwen.paths import isolated_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    try:
        profile = isolated_profile(args.profile)
    except ValueError as error:
        parser.error(str(error))
    IBus.init()
    bus = IBus.Bus.new()
    if not bus.is_connected():
        raise RuntimeError("Cannot connect to IBus")
    RiwenEngine.native = NativeRime(project, profile)
    voice = VoiceControl(project, os.environ.get("RIWEN_VOICE_CONTROL_DIR", profile),
                         os.environ.get("RIWEN_VOICE", "0") == "1")
    RiwenEngine.voice = voice.controller
    factory = IBus.Factory.new(bus.get_connection())
    factory.add_engine("riwen", RiwenEngine)
    component = IBus.Component.new(
        "org.freedesktop.IBus.Riwen", "Riwen experimental", "0.1", "", "", "", "", "",
    )
    component.add_engine(IBus.EngineDesc.new(
        "riwen", "Riwen · " + RiwenEngine.native.scheme["name"], "Local Qwen candidate ranking",
        "zh_CN", "", "", "", "us",
    ))
    if not bus.register_component(component):
        raise RuntimeError("IBus component registration failed")
    loop = GLib.MainLoop()
    bus.connect("disconnected", lambda *_: loop.quit())
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (loop.quit(), False)[1])
    print("Riwen engine registered; no input source was switched.", flush=True)
    try:
        loop.run()
    finally:
        voice.close()
        for engine in list(RiwenEngine.instances):
            engine.shutdown()
        factory.destroy()
        RiwenEngine.native.lib.riwen_finalize()


if __name__ == "__main__":
    main()
