"""Experimental IBus frontend: all Rime calls and idle redraws share one main loop."""
import time
import weakref

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402


class RiwenEngine(IBus.Engine):
    __gtype_name__ = "RiwenExperimentalEngine"
    native = None
    instances = weakref.WeakSet()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = self.native.create()
        self.focused = False
        self.private = False
        self.timer = 0
        self.serial = 0
        self.poll_until = 0
        self.last = {}
        self.native.property(self.session, "riwen_mode", "off")
        self.instances.add(self)

    def bump(self, name):
        self.serial += 1
        self.native.property(self.session, name, self.serial)

    def stop_timer(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def reset_context(self):
        self.stop_timer()
        self.bump("riwen_reset")

    def render(self, state):
        if state["commit"]:
            self.commit_text(IBus.Text.new_from_string(state["commit"]))
        preedit = state["preedit"]
        cursor = len(preedit.encode()[:state["cursor"]].decode("utf-8", errors="ignore"))
        self.update_preedit_text(IBus.Text.new_from_string(preedit), cursor, bool(preedit))
        table = IBus.LookupTable.new(8, state["selected"], True, False)
        table.set_orientation(IBus.Orientation.HORIZONTAL)
        choice = state["qwen_choice"]
        for candidate in state["candidates"]:
            display = candidate
            if choice and candidate == choice:
                display += " 〔Qwen〕"
                choice = ""  # Annotate only one entry if a later filter duplicates it.
            table.append_candidate(IBus.Text.new_from_string(display))
        self.update_lookup_table(table, bool(state["candidates"]))
        self.last = state

    def schedule(self, state):
        self.stop_timer()
        if self.focused and not self.private and state["status"] in ("pending", "pending-correction"):
            self.poll_until = time.monotonic() + (4 if state["status"] == "pending-correction" else 2)
            self.timer = GLib.timeout_add(40, self.poll, priority=GLib.PRIORITY_DEFAULT_IDLE)

    def poll(self):
        if not self.focused or self.private or time.monotonic() >= self.poll_until:
            self.timer = 0
            return GLib.SOURCE_REMOVE
        self.bump("riwen_poll")
        state = self.native.state(self.session)
        if (state["candidates"] != self.last.get("candidates") or
                state["qwen_choice"] != self.last.get("qwen_choice")):
            self.render(state)
        if state["status"] not in ("pending", "pending-correction"):
            self.timer = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def do_process_key_event(self, keyval, keycode, modifiers):
        if not self.focused or self.private:
            return False
        if modifiers & (IBus.ModifierType.SUPER_MASK | IBus.ModifierType.MOD4_MASK):
            self.reset_context()
            return False
        mask = modifiers & int(IBus.ModifierType.SHIFT_MASK | IBus.ModifierType.LOCK_MASK |
                               IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK |
                               IBus.ModifierType.RELEASE_MASK)
        handled = self.native.lib.riwen_key(self.session, keyval, mask)
        state = self.native.state(self.session)
        self.render(state)
        self.schedule(state)
        return bool(handled)

    def do_focus_in(self):
        self.focused = True
        self.reset_context()
        self.native.property(self.session, "riwen_mode", "off" if self.private else "auto")

    def do_focus_out(self):
        self.focused = False
        self.reset_context()
        self.native.property(self.session, "riwen_mode", "off")
        self.native.lib.riwen_clear(self.session)
        self.last = {}

    def do_disable(self):
        self.do_focus_out()

    def do_reset(self):
        self.reset_context()
        self.native.lib.riwen_clear(self.session)
        self.render(self.native.state(self.session))

    def do_set_content_type(self, purpose, hints):
        self.private = purpose in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN) or bool(hints & IBus.InputHints.PRIVATE)
        self.reset_context()
        self.native.property(self.session, "riwen_mode", "auto" if self.focused and not self.private else "off")
        if self.private:
            self.native.lib.riwen_clear(self.session)
            self.render(self.native.state(self.session))

    def do_candidate_clicked(self, index, button, state):
        if self.focused and not self.private:
            self.stop_timer()
            self.native.lib.riwen_choose(self.session, index)
            self.render(self.native.state(self.session))

    def do_page_up(self):
        self.do_process_key_event(IBus.KEY_Page_Up, 0, 0)

    def do_page_down(self):
        self.do_process_key_event(IBus.KEY_Page_Down, 0, 0)

    def do_cursor_up(self):
        self.do_process_key_event(IBus.KEY_Up, 0, 0)

    def do_cursor_down(self):
        self.do_process_key_event(IBus.KEY_Down, 0, 0)

    def shutdown(self):
        self.stop_timer()
        if self.session:
            self.native.lib.riwen_destroy(self.session)
            self.session = 0

    def do_destroy(self):
        self.shutdown()
        IBus.Engine.do_destroy(self)
