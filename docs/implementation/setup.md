# Setup and compatibility

## RPM installation and normal use

The current target is **GNOME 51 / Fedora x86_64**. Build for the Fedora release
where the package will run; it contains a native librime bridge.

```sh
python3 scripts/package-rpm.py
python3 tests/rpm-package.py
sudo dnf install ./dist/riwen-0.1.0-1.fc45.x86_64.rpm
```

The builder needs Python 3, `rpm-build`, GCC C++, `glib2`, and librime headers.
Normal RPM builders install `librime-devel`; the local helper can extract the
exact matching devel RPM privately when headers are absent. Its `--nodeps` flag
in that case bypasses **build** dependency checking only; all runtime RPM
requirements remain declared and installation must use normal dependency checks.
It does not install packages or touch the desktop. Binary and source RPMs go to
`dist/`. The source RPM uses the standard declared build dependencies when rebuilt.

The RPM requires Python >= 3.12, PyYAML, Python GI, IBus/Rime, librime-lua,
LuaSocket, curl, uv, PipeWire tools and the Vulkan loader. It includes neither Bun
nor uv binaries. Models, llama.cpp and the private ASR environment are downloaded
only during user-level preparation. The repository has not declared a license for
Riwen itself; the local prototype RPM records `LicenseRef-riwen-unlicensed AND MIT`
(the migrated voice code is MIT). A redistribution license must be resolved before
publishing this prototype package to a repository.

After installation, sign out/back in and enable **Riwen — Local Qwen for Rime** in
GNOME Extensions. RPM scriptlets do not enable it, start services or switch IBus.
Before switching from a user-installed ZIP, stop and explicitly uninstall that
copy of `riwen-badge@riwen`; a user extension overrides the system copy. Preserve
any models or learned isolated profiles you want to migrate. Automatic migration
of the old per-extension data directory is not implemented.

Use `riwen start`, `riwen stop`, `riwen status` and `riwen schemas` for terminal
control. In a checkout use `python3 scripts/app.py start` (or the developer alias
`bun start`). Ctrl+C/stop restores the previous engine before tearing down owned
process groups. Preparation and input-source switching happen only on user start.

RPM code is read-only under `/usr/lib64/riwen`; the UI is under
`/usr/share/gnome-shell/extensions/riwen-badge@riwen`. Models, the ASR environment
and isolated Rime profile use `$XDG_DATA_HOME/riwen`, normally
`~/.local/share/riwen`. Runtime sockets, status and `app.log` use
`$XDG_RUNTIME_DIR/riwen`; without that environment variable they use `session/`
below the data root. `RIWEN_DATA_DIR` and `RIWEN_SESSION_DIR` override those paths.
Checkout/ZIP runs retain `.cache` below the app root. Stop Riwen before upgrading;
sign out/back in to reload extension code. Uninstall leaves per-user data intact.

The launcher reuses a healthy Qwen3-1.7B server on port 18080, or starts an owned
model on an available port. It never stops a reused model. A lock prevents duplicate
sessions; a user-only Unix socket receives stop/status requests. Manual input-source
changes during a session are preserved at shutdown. Typing is never logged.

`tests/rpm-package.py` uses bubblewrap's read-only overlay support to mount the
actual RPM at its `/usr` paths and stage its matching Lua plugin dependency if
needed. It removes Bun from PATH and runs the Python launcher against a deterministic
model on a private D-Bus/IBus session. No system RPM installation is performed.

## Optional GNOME extension ZIP

`python3 scripts/package-extension.py` builds
`dist/riwen-badge@riwen.shell-extension.zip`. It includes the GJS UI and Python app
sources, with no Bun or uv executables. It is an alternative local bundle, not a
publication to extensions.gnome.org. The RPM is the preferred distribution format.

`python3 scripts/install-badge.py` builds and installs the ZIP contents under
`$XDG_DATA_HOME/gnome-shell/extensions/riwen-badge@riwen` and queues enablement for
the next login. Stop its backend before updating. Unlike the RPM, this bundle
prepares native support on first use and needs `g++`, `rpm`, `dnf download`,
`rpm2cpio`, `cpio`, and `curl`, in addition to Python/PyYAML/GI, IBus/Rime,
LuaSocket, uv and PipeWire. Its `.cache` lives below `app/`. The local installer can
reuse immutable model assets from the checkout without depending on its path.

## Local voice runtime

Voice is prepared lazily from the panel or the first F10; starting Riwen does not
open the microphone. The system uv package provisions managed Python 3.12 into a private
`voice-venv` below Riwen's data directory (`.cache` for checkout/ZIP), with `sherpa-onnx==1.13.4` and `numpy==2.2.6`. This avoids
coupling ASR wheels to the system Python/GI version (the inspected system is
Python 3.15, while the previous ibus-voice wheelhouse was built for 3.14).
Install `uv` on PATH; `python3 scripts/prepare-voice.py` prepares only this
runtime. The complete app prepares both runtime and model when requested.

Qwen3-ASR uses the checksum-pinned sherpa-onnx 0.6B INT8 release dated 2026-03-25.
Model files live under `voice-models` below that data directory; `RIWEN_ASR_MODEL_DIR` overrides the
model root. The worker first checks `~/.local/share/ibus-voice/models` and copies
or hardlinks a complete matching model. Otherwise it downloads the approximately
879 MB archive and verifies SHA-256 before extraction. The installer also reuses
the checkout's prepared model without linking the extension to its path. Python
environments are created per installation rather than copied between locations.

The voice worker keeps all audio in bounded memory, uses PipeWire's default
source at mono 16 kHz, and runs CPU recognition outside IBus. There are no cloud
API keys, clipboard injection, audio files, transcript logs or history databases.
First preparation needs network access; subsequent inference is offline. Runtime
and model licenses/notices are in `docs/third-party` and the package's `runtime`.

`bun run test:voice` tests cancellation, focus/private checks, recorder bounds and
failure recovery without a microphone. `bun run test:ibus --voice` exercises F10,
Esc and text commit on a private IBus bus with a deterministic speech worker.
These tests do not record ambient audio. Model checks can use the public WAVs
included in the model's `test_wavs` folder; actual microphone and Shell popup
behavior still need a manual trial.

## Rime scheme selection

`python3 scripts/runtime.py schemas` enumerates standalone compiled schemas under the
user profile's `build/`. Auto selects `user.yaml`'s previously selected scheme,
then the first available scheme in `default.yaml`'s `schema_list`. CLI overrides:
`RIWEN_SCHEMA`, `RIWEN_RIME_SOURCE`, `RIWEN_CORRECTION=0`, and `RIWEN_CPU=1`.
The extension exposes these through its scheme chooser and preferences.

Preparation copies compiled static assets and optional Lua/OpenCC files into an
isolated profile. It inserts Riwen before existing filters so pin/presentation
filters retain precedence, rather than requiring a particular pin filter. Script
schemes allow limited corrections; table schemes rank only. The scheme's speller
alphabet and delimiters govern requests. Ordinary table, phrase, user_phrase and
sentence candidates are eligible; custom user_table and high-priority candidates
are still excluded. Learned databases are not imported from the original profile.

The commands below are for development and troubleshooting.

## Inspected environment

- GNOME Wayland; active IBus engine `rime`.
- Profile `~/.config/ibus/rime`; scheme `rime_frost_double_pinyin_flypy`; page size 8.
- Core Ultra 9 185H, 30 GiB usable RAM, RTX 4060 Laptop with 8 GiB VRAM.
- Installed `/usr/bin/llama-server` reports ROCm and no usable GPU.
- Running Ollama reports 0.6.2; this prototype does not depend on it.
- System `librime.so.1` (1.16.1) registers core/gears but not `lua`. Schema Lua
  entries alone do not prove runtime support. The isolated native bridge loads
  Fedora's matching `librime-lua` plugin explicitly; this works with real Rime.
- Standalone Lua 5.5 and LuaSocket are installed. A different embedded Lua version
  needs a matching LuaSocket binary.

## Model runtime

`python3 scripts/runtime.py runtime-download` installs a checksum-pinned upstream llama.cpp b10964
Vulkan release into `.cache/llama-vulkan`. It recognizes both the Intel integrated
GPU and the RTX 4060. The launcher prefers this cached runtime and selects NVIDIA
when detected; `RIWEN_DEVICE` overrides the choice. No system binary is replaced.

Use a recent llama.cpp server with NVIDIA CUDA or Vulkan support. Set
`RIWEN_LLAMA_SERVER=/absolute/path/to/llama-server` before
`python3 scripts/runtime.py model-start`
for an isolated runtime. The launcher checks GPU availability; pass `--cpu` for an
explicit CPU baseline. Model download verifies SHA-256 and reuses valid files.
An interrupted `.part` file is rejected: remove it and retry.

The launcher uses 2,048 context tokens, one slot, six CPU threads, thinking disabled,
and port 18080. The bridge's deadline is 1.2 seconds. Slow backends fall back.

## Checkout native runtime and IBus frontend

```sh
bun run rime:prepare
bun run test:rime
bun run test:ibus
bun run ibus:prepare
```

The preparation helper currently targets this Fedora x86_64 setup. It needs `rpm`,
`dnf download`, `rpm2cpio`, `cpio`, and `g++`, plus installed librime, LuaSocket,
Python GI with IBus typelibs, IBus, and `dbus-run-session` for frontend tests.
It downloads `librime-devel` and `librime-lua` matching the installed librime RPM
release, extracts them into a staging directory, and compiles the local bridge. Native outputs are
replaced atomically, so rebuilding does not overwrite a mapped shared library.
No RPM is installed and no system library is replaced. If the matching release is
absent from the Fedora repository, preparation fails rather than mixing versions.

`ibus:prepare` copies compiled static assets from `~/.config/ibus/rime` (or
`$XDG_CONFIG_HOME/ibus/rime`) into `.cache/ibus-profile`. It selects a deployed scheme and inserts Riwen before existing filters. Learned user databases are not copied;
the experimental engine learns separately in its own profile. Reprepare only
while the experimental frontend is stopped.

The inspected `aux_code.lua` reassigns generic-for variables, which Lua 5.5 rejects.
Preparation adapts those assignments in the **copied** script. The active profile
is untouched. Real-Rime tests verify the plugin can load LuaSocket and the scheme.

For manual checkout control, run `python3 scripts/runtime.py model-start`,
`python3 scripts/runtime.py bridge`, and
`python3 src/ibus/main.py --profile .cache/ibus-profile` in separate terminals
after preparation. `ibus:start` only
registers `riwen`; select it with `ibus engine riwen`, and switch back with
`ibus engine rime` before stopping it. The frontend refuses profiles outside
Riwen's private data directory. This manual frontend has no autostart or persistent
input-source installation; the GNOME extension provides managed startup.
`python3 scripts/app.py start` performs these steps for normal use, with automatic cleanup.

`test:ibus` runs a separate daemon on a private D-Bus session and socket, with
isolated XDG paths. It selects Riwen **only on that private bus**. Add `--model` to
use the local Qwen endpoint instead of a deterministic ranker. `rime:demo` also
uses Qwen, but drives the native probe without IBus. Both accept
`RIWEN_MODEL_URL=http://127.0.0.1:PORT/v1/chat/completions`; neither needs a separate
`bridge:start` process because each creates an ephemeral bridge.

## Stock IBus Rime: stage before installation

`python3 scripts/runtime.py stage` generates files for the detected/selected deployed scheme in
`.cache/rime-stage`. `RIWEN_SCHEMA` overrides the scheme. The staged patch prepends
Riwen and preserves the compiled filter list; merge it with current customizations
and restage after changing those filters. Staging does not install or redeploy anything.

For the stock IBus Rime path, provide a Lua-enabled librime compatible with IBus and verify
`require('socket')` **inside that Rime process**. Standalone Lua success is not
sufficient. Do not substitute incompatible shared libraries system-wide.

For intentional installation:

1. Back up existing customizations.
2. Copy staged `lua/riwen.lua` into the Rime user directory's `lua/` folder.
3. Merge patch keys into `<schema_id>.custom.yaml`, preserving
   existing `patch:` entries.
4. Redeploy through the Rime menu and test in a disposable ordinary text field.
5. To remove, remove only Riwen's two engine entries and `riwen/port`, redeploy,
   stop local processes, and optionally delete `lua/riwen.lua`.

## Sources

Context7 was over quota. Upstream documentation and installed IBus GI/C API
introspection were used:

- For the badge, Context7 remained over quota. The installed GNOME Shell 51.rc
  sources (`ui/ibusCandidatePopup.js`, `misc/ibusManager.js`,
  `extensions/extension.js`, and `ui/extensionSystem.js`) were inspected via
  `gresource extract /usr/lib64/gnome-shell/libshell-51.so` under
  `/org/gnome/shell/`. They confirm plain-text candidates, the extension method
  wrapper API, and discovery of local extensions at Shell startup. Badge tests
  cover candidate/page changes, engine isolation, teardown, and text fallback;
  actual Shell appearance still needs a visual check after the next login.
  Panel/menu APIs were checked against installed `ui/panelMenu.js` and
  `ui/popupMenu.js`; preference widgets use the installed Adwaita/Gio APIs.
  Context7 was unreachable during this integration work.
  For the centered panel popup and bundled symbolic icon, Context7 was over quota;
  installed GNOME 51 `ui/panelMenu.js` and `ui/boxpointer.js` confirmed the `0.5`
  menu alignment and monitor-edge clamping. The upstream
  [GJS widget guide](https://gjs.guide/extensions/topics/st-widgets.html) documents
  the theme-sized `St.Icon` with `system-status-icon` styling.

- [librime-lua](https://github.com/hchunhui/librime-lua), including `src/types.cc`.
- [IBus key events](https://github.com/rime/ibus-rime/blob/master/rime_engine.c)
  and [notifications](https://github.com/rime/ibus-rime/blob/master/rime_main.c).
- Python migration: Context7 remained over quota. Upstream references used:
  [asyncio tasks/cancellation](https://docs.python.org/3/library/asyncio-task.html),
  [HTTPConnection](https://docs.python.org/3/library/http.client.html), and
  [PyYAML safe loading](https://pyyaml.org/wiki/PyYAMLDocumentation).
- RPM build sections/dependencies were checked against the
  [RPM spec manual](https://rpm.org/docs/latest/manual/spec.html).
  Bubblewrap overlay options were checked with the installed `bwrap --help`.
- [Python process ownership](https://docs.python.org/3/library/subprocess.html),
  including `start_new_session`; Context7 was still over quota for the launcher.
- [LuaSocket UDP](https://lunarmodules.github.io/luasocket/udp.html).
- [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
- [Qwen3 model](https://huggingface.co/Qwen/Qwen3-1.7B).
- [Q4_K_M weights](https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF).
- Voice Context7 lookup also exceeded quota. The sibling project's working
  Qwen3-ASR adapter, installed sherpa-onnx API and public sample WAVs were used,
  with [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx),
  [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR), and
  [uv Python management](https://docs.astral.sh/uv/guides/install-python/)
  as upstream references. `pw-record --help` verified capture options.
