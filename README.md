# Riwen

Local Qwen-powered 候选词 ranking and phrase correction for **IBus + Rime**,
with local voice dictation, a GNOME panel UI and colored Qwen badges.

## Install and use

On **GNOME 51 / Fedora x86_64** with an already-deployed IBus Rime profile,
install the Riwen RPM. It installs the Python backend, a prebuilt native bridge,
and the GNOME extension together:

```sh
sudo dnf install ./dist/riwen-0.1.0-1.fc45.x86_64.rpm
```

Use the RPM built for your Fedora release. Sign out and back in, then enable
**Riwen — Local Qwen for Rime** in GNOME Extensions. Installation itself does not
start Riwen, enable the extension, or change your input method. Once enabled,
Riwen prepares its local Qwen model (first download about 1.3 GB). The panel shows
setup status, a scheme chooser, an on/off switch, and settings. Turning assistance
off restores the previous input method.

**No Bun or Node.js is required at runtime.** Python, PyYAML, GI/IBus, Rime,
LuaSocket, uv and PipeWire tools are declared RPM dependencies. Model inference
runs in a separate llama.cpp process; voice uses a private Python ASR environment.

The default follows your last-used/default **deployed Rime scheme**. Full pinyin,
other double-pinyin schemes, and table schemes no longer require the 小鹤 ID or
雾凇's `pin_cand_filter`. Ranking uses the scheme's alphabet and ordinary native
candidates. Phonetic/script schemes can also offer limited long-phrase correction;
shape/table schemes use ranking only. Choose a scheme, then **Restart to apply
settings**. Original candidates remain selectable; candidate assistance never commits for you.

**Voice input:** open the Riwen panel → **Prepare voice model**, then focus a text
field and press **F10** to start speaking. Press **F10** again to recognize and
insert the text; **Esc** cancels. The local Qwen3-ASR backend is migrated from
[ibus-voice](https://github.com/stonega/ibus-voice), works independently of the
selected Rime scheme, and reuses its downloaded model when available. Otherwise
first use downloads about 879 MB plus a private Python runtime. No audio or
transcript history is saved. Voice is available through Riwen's frontend, not the
standalone Lua filter in stock IBus Rime.

The app writes models and its isolated Rime profile to
`$XDG_DATA_HOME/riwen` (normally `~/.local/share/riwen`), and session control/status
to `$XDG_RUNTIME_DIR/riwen`. It does not write into `/usr` or overwrite your Rime
configuration. Stop assistance before an upgrade, then sign out/back in to reload
the extension. Existing user-installed ZIP extensions with the same UUID must be
removed explicitly before switching to the system RPM, because they take priority.

For terminal use, run `riwen start` / `riwen stop`. From a checkout, use
`python3 scripts/app.py start` / `python3 scripts/app.py stop`.
`RIWEN_SCHEMA=your_schema_id` selects a deployed scheme.

[Usage](docs/user/usage.md) · [System requirements / advanced setup](docs/implementation/setup.md)
· [Architecture](docs/design/architecture.md) · [Measured results](docs/implementation/benchmark.md)

## Development

```sh
bun install
bun run check
bun run test:python
bun test
bun run test:lua
bun run rime:prepare
bun run test:rime
bun run test:ibus
bun run test:ibus --correction
bun run test:voice
bun run test:ibus --voice
bun run test:launcher
bun run test:extension
bun run extension:package
bun run test:extension:package
python3 scripts/package-rpm.py
python3 tests/rpm-package.py
```

Integration checks use private IBus sessions and leave the desktop input source
alone. The launcher test covers startup, automatic selection, candidate updates,
duplicate starts, and restoring the previous engine on stop. GNOME's visual
rendering still needs an interactive trial.

Bun and Biome are developer tools for the remaining JavaScript/TypeScript test
harnesses. They are not shipped or used by the installed app. The RPM test mounts
the real payload read-only and runs the launcher on a private bus with no Bun on
PATH. See the setup notes for build dependencies and separate service commands. Stock IBus Rime can use the
staged Lua extension with **F8** instead of the experimental frontend.
