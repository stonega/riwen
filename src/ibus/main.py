"""Register an experimental engine for this IBus connection; never switch engines."""
import argparse
import signal
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, GLibUnix, IBus  # noqa: E402
from engine import RiwenEngine  # noqa: E402
from native import NativeRime  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    profile = Path(args.profile).resolve()
    # Deliberately refuse the user's ordinary Rime directory.
    if not profile.is_relative_to(project / ".cache"):
        parser.error("Experimental profile must be under the project's .cache")
    IBus.init()
    bus = IBus.Bus.new()
    if not bus.is_connected():
        raise RuntimeError("Cannot connect to IBus")
    RiwenEngine.native = NativeRime(project, profile)
    factory = IBus.Factory.new(bus.get_connection())
    factory.add_engine("riwen", RiwenEngine)
    component = IBus.Component.new(
        "org.freedesktop.IBus.Riwen", "Riwen experimental", "0.1", "", "", "", "", "",
    )
    component.add_engine(IBus.EngineDesc.new(
        "riwen", "Riwen 小鹤 (experimental)", "Local Qwen candidate ranking",
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
        for engine in list(RiwenEngine.instances):
            engine.shutdown()
        factory.destroy()
        RiwenEngine.native.lib.riwen_finalize()


if __name__ == "__main__":
    main()
