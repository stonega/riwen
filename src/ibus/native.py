"""Small ctypes wrapper; callers must serialize operations on the IBus main loop."""
import ctypes
import json
from pathlib import Path


class NativeRime:
    def __init__(self, project: Path, profile: Path):
        root = project / ".cache/rime-native"
        self.lib = ctypes.CDLL(str(root / "libriwen-rime.so"), mode=ctypes.RTLD_GLOBAL)
        u64, integer, text = ctypes.c_uint64, ctypes.c_int, ctypes.c_char_p
        signatures = {
            "init": ([text, text], text), "version": ([], text),
            "create": ([text], u64), "destroy": ([u64], None),
            "finalize": ([], None), "key": ([u64, integer, integer], integer),
            "property": ([u64, text, text], None), "clear": ([u64], None),
            "choose": ([u64, integer], integer), "state": ([u64], text),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, f"riwen_{name}")
            fn.argtypes, fn.restype = args, result
        error = self.lib.riwen_init(
            str(profile).encode(),
            str(root / "root/usr/lib64/rime-plugins/librime-lua.so").encode(),
        )
        if error:
            raise RuntimeError(error.decode())

    def create(self):
        session = self.lib.riwen_create(b"rime_frost_double_pinyin_flypy")
        if not session:
            raise RuntimeError("Could not create Riwen's Rime session")
        return session

    def property(self, session, name, value):
        self.lib.riwen_property(session, name.encode(), str(value).encode())

    def state(self, session):
        return json.loads(self.lib.riwen_state(session))
