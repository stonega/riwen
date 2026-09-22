"""Separate RPM-owned code from per-user writable data."""
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
PACKAGED = (PROJECT / "rpm-layout.json").is_file()
LAYOUT = {}
if PACKAGED:
    LAYOUT = json.loads((PROJECT / "rpm-layout.json").read_text())
DATA = Path(os.environ.get("RIWEN_DATA_DIR") or (
    Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "riwen"
    if PACKAGED else PROJECT / ".cache"
)).resolve()
default_session = DATA
if PACKAGED:
    default_session = (Path(os.environ["XDG_RUNTIME_DIR"]) / "riwen"
                       if os.environ.get("XDG_RUNTIME_DIR") else DATA / "session")
SESSION = Path(os.environ.get("RIWEN_SESSION_DIR") or default_session).resolve()
NATIVE = PROJECT / "native" if PACKAGED else DATA / "rime-native"
PLUGIN = Path(LAYOUT.get("rime_plugin", NATIVE / "root/usr/lib64/rime-plugins/librime-lua.so"))


def isolated_profile(value):
    profile = Path(value).resolve()
    if profile == DATA or not profile.is_relative_to(DATA):
        raise ValueError("Riwen profile must be inside its private data directory")
    return profile
