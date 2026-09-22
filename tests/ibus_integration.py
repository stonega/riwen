"""Runs under dbus-run-session, with a private IBus address and isolated XDG dirs."""
import os
import json
import selectors
import subprocess
import sys
import time
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import Gio, GLib, IBus  # noqa: E402

profile = Path(sys.argv[1]).resolve()
launcher = "--launcher" in sys.argv
chosen_word = "城市" if "--prefer-first" in sys.argv else "程式"
correction = "--correction" in sys.argv
voice = "--voice" in sys.argv
if correction:
    chosen_word = "这是怎么回事"
project = Path(os.environ.get("RIWEN_TEST_APP", Path(__file__).resolve().parents[1]))
address = f"unix:path={profile}/ibus.sock"
env = dict(os.environ, IBUS_ADDRESS=address,
           IBUS_USE_PORTAL="0", GIO_USE_VFS="local", GSETTINGS_BACKEND="memory",
           XDG_CONFIG_HOME=str(profile / "xdg-config"),
           XDG_CACHE_HOME=str(profile / "xdg-cache"),
           XDG_DATA_HOME=str(profile / "xdg-data"))
env.pop("DISPLAY", None)
env.pop("WAYLAND_DISPLAY", None)
os.environ.update({key: env[key] for key in ("IBUS_ADDRESS", "IBUS_USE_PORTAL", "GIO_USE_VFS", "GSETTINGS_BACKEND", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")})
daemon = subprocess.Popen(["ibus-daemon", "--single", "--emoji-extension=disable", "--cache=none", f"--address={address}"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
frontend = None
frontend_failure = False
loop_context = GLib.MainContext.default()


def drain():
    while loop_context.pending():
        loop_context.iteration(False)


def wait_for(predicate, description, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        drain()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError(f"Timed out waiting for {description}")


try:
    wait_for(lambda: (profile / "ibus.sock").exists(), "private IBus daemon")
    IBus.init()
    bus = IBus.Bus.new()
    wait_for(bus.is_connected, "private IBus connection")
    if launcher:
        assert bus.set_global_engine("xkb:us::eng"), "Could not select original private-bus engine"
    command = ([sys.executable, str(project / "scripts/app.py"), "start"] if launcher else
               [sys.executable, str(Path(__file__).with_name("voice_fixture_frontend.py") if voice else
                                    project / "src/ibus/main.py"), "--profile", str(profile)])
    frontend = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    with selectors.DefaultSelector() as selector:
        selector.register(frontend.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + (40 if launcher else 5)
        marker = "Riwen is ready" if launcher else "registered"
        while time.monotonic() < deadline:
            if selector.select(0.1):
                line = frontend.stdout.readline()
                if marker in line:
                    break
                if not line:
                    raise AssertionError("Frontend exited before readiness")
        else:
            raise AssertionError("Frontend registration timed out")
    if launcher:
        assert bus.get_global_engine().get_name() == "riwen", "Launcher did not switch engines"
        duplicate = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
        assert duplicate.returncode == 1 and "already running" in duplicate.stderr
        status = subprocess.run([sys.executable, str(project / "scripts/app.py"), "status"], env=env,
                                capture_output=True, text=True, timeout=5)
        status = json.loads(status.stdout)
        assert status["running"] and status["phase"] == "ready" and status["schema"]
        print("PASS: one command selects Riwen; duplicate launch is harmless", flush=True)

    context = bus.create_input_context("riwen-integration-test")
    context.set_capabilities(int(IBus.Capabilite.PREEDIT_TEXT | IBus.Capabilite.AUXILIARY_TEXT | IBus.Capabilite.LOOKUP_TABLE | IBus.Capabilite.FOCUS))
    menu, commits = [], []
    auxiliary = []

    def signal_message(_connection, _sender, _path, _interface, name, parameters):
        data = parameters.unpack()
        if name == "UpdateLookupTable":
            table, visible = data
            menu[:] = [text[2] for text in table[7]] if visible else []
        elif name == "CommitText":
            commits.append(data[0][2])
        elif name == "UpdateAuxiliaryText":
            auxiliary[:] = [data[0][2]] if data[1] else []

    # Subscribe to wire messages to avoid PyGObject ownership issues with borrowed
    # IBusSerializable signal arguments on the installed development GI version.
    bus.get_connection().signal_subscribe(None, "org.freedesktop.IBus.InputContext", None,
        context.get_object_path(), None, Gio.DBusSignalFlags.NONE, signal_message)
    assert bus.set_global_engine("riwen"), "Could not select Riwen on private bus"
    context.focus_in()
    context.set_engine("riwen")
    wait_for(lambda: context.get_engine() and context.get_engine().get_name() == "riwen", "Riwen selection on the private bus")

    def key(value):
        result = context.process_key_event(value, 0, 0)
        if value == IBus.KEY_F10:
            context.process_key_event(value, 0, int(IBus.ModifierType.RELEASE_MASK))
        drain()
        return result

    def type_input(text):
        for char in text:
            key(ord(char))

    type_input("woxpleyige")
    key(32)
    wait_for(lambda: commits and commits[-1] == "我写了一个", "native context commit")
    type_input("veuizfmhhvui" if correction else "igui")
    wait_for(lambda: menu and menu[0] == chosen_word + " 〔Qwen〕", "automatic idle Qwen badge")
    assert all("〔Qwen〕" not in candidate for candidate in menu[1:]), menu
    if correction:
        assert "这是怎忙会是" in menu, "Original phrase disappeared"
    key(32)
    wait_for(lambda: commits[-1] == chosen_word, "suggestion commits without its badge")
    print("PASS: idle menu shows one Qwen badge; committed text has no badge", flush=True)

    # Focus changes clear commit history; a new field must not inherit it.
    context.focus_out()
    context.focus_in()
    drain()
    type_input("igui")
    wait_for(lambda: bool(menu), "new-field menu")
    baseline = list(menu)
    assert all("〔Qwen〕" not in candidate for candidate in baseline), baseline
    until = time.monotonic() + 0.35
    while time.monotonic() < until:
        drain(); time.sleep(0.005)
    assert menu == baseline, menu
    print("PASS: focus change drops previous context", flush=True)

    if voice:
        context.reset()
        prepare = subprocess.run([sys.executable, str(project / "scripts/app.py"), "voice-prepare"],
                                 env=dict(env, RIWEN_SESSION_DIR=str(profile)), capture_output=True, text=True, timeout=5)
        assert json.loads(prepare.stdout)["ok"]
        def voice_ready():
            try:
                return json.loads((profile / "voice-status.json").read_text())["phase"] == "ready"
            except (OSError, ValueError): return False
        wait_for(voice_ready, "voice model preparation control")
        key(IBus.KEY_F10)
        wait_for(lambda: auxiliary == ["Listening"], "voice recording indicator")
        key(IBus.KEY_F10)
        wait_for(lambda: commits[-1] == "语音输入测试", "voice transcript commit")
        before = len(commits)
        wait_for(voice_ready, "voice ready after commit")
        key(IBus.KEY_F10)
        wait_for(lambda: auxiliary == ["Listening"], "second dictation")
        key(IBus.KEY_F10)
        context.focus_out()
        context.focus_in()
        until = time.monotonic() + 0.4
        while time.monotonic() < until:
            drain(); time.sleep(0.005)
        assert len(commits) == before, "Late speech reached refocused field"
        key(IBus.KEY_F10)
        wait_for(lambda: auxiliary == ["Listening"], "cancel test recording")
        key(IBus.KEY_Escape)
        wait_for(voice_ready, "cancelled recording")
        wait_for(lambda: not auxiliary, "cancel hides voice indicator")
        context.process_key_event(IBus.KEY_F10, 0, 0)
        wait_for(lambda: auxiliary == ["Listening"], "held F10 recording")
        context.process_key_event(IBus.KEY_F10, 0, 0)
        drain()
        assert auxiliary == ["Listening"], "F10 autorepeat stopped dictation"
        context.process_key_event(IBus.KEY_F10, 0, int(IBus.ModifierType.RELEASE_MASK))
        type_input("wo")
        wait_for(voice_ready, "typing cancels dictation")
        assert len(commits) == before, "Cancelled speech was committed"
        context.reset()
        key(IBus.KEY_F10)
        wait_for(lambda: auxiliary == ["Listening"], "panel cancel recording")
        cancelled = subprocess.run([sys.executable, str(project / "scripts/app.py"), "voice-cancel"],
                                   env=dict(env, RIWEN_SESSION_DIR=str(profile)), capture_output=True, text=True, timeout=5)
        assert json.loads(cancelled.stdout)["ok"]
        wait_for(voice_ready, "panel cancelled recording")
        type_input("wo")
        wait_for(lambda: bool(menu), "Rime typing after voice")
        baseline = list(menu)
        key(IBus.KEY_F10)
        assert menu == baseline, "Voice destroyed a Rime composition"
        context.reset()
        print("PASS: voice commits once, cancels on focus/Esc, and preserves Rime typing", flush=True)

    for purpose, hints in [(IBus.InputPurpose.PASSWORD, 0), (IBus.InputPurpose.PIN, 0),
                           (IBus.InputPurpose.FREE_FORM, IBus.InputHints.PRIVATE)]:
        context.reset()
        context.set_content_type(purpose, hints)
        drain()
        assert not key(ord("a")), "Private field key was captured"
        if voice:
            assert not key(IBus.KEY_F10), "Voice shortcut captured in private field"
    print("PASS: password/PIN/private fields bypass Rime and ranking", flush=True)

    context.destroy()
    if launcher:
        stop = subprocess.run([sys.executable, str(project / "scripts/app.py"), "stop"], env=env,
                              capture_output=True, text=True, timeout=5)
        assert stop.returncode == 0, stop.stderr
        frontend.wait(timeout=15)
        assert frontend.returncode == 0, "Launcher did not stop cleanly"
        assert bus.get_global_engine().get_name() == "xkb:us::eng", "Original engine was not restored"
        assert not (Path(env.get("RIWEN_SESSION_DIR", project / ".cache")) / "app.sock").exists(), "Control socket leaked"
        print("PASS: stop restores the previous engine and removes the control socket", flush=True)
finally:
    if frontend:
        frontend.terminate()
        try:
            _, errors = frontend.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            frontend.kill(); _, errors = frontend.communicate()
        if errors.strip():
            print(errors, file=sys.stderr)
            # Any Python traceback or Lua error invalidates this integration test.
            if "Traceback" in errors or " error" in errors:
                frontend_failure = True
    daemon.terminate()
    try:
        daemon.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        daemon.kill(); daemon.communicate()

if frontend_failure:
    raise AssertionError("Frontend reported an integration error")
