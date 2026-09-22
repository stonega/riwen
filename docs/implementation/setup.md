# Setup and compatibility

## Normal use

Run `bun start` from the project directory. This is the complete foreground app:
it prepares its own profile, downloads missing model/runtime files, waits for
services to become ready, and selects Riwen through the IBus API. Ctrl+C or
`bun run stop` restores the previous engine before shutting down owned services.
No separate setup commands are needed on the inspected machine.

The launcher uses `.cache/app-profile` and a private local UDP port. It reuses a
healthy Qwen3-1.7B server on port 18080, or starts its own model on an available
port. It never stops a reused model. A lock prevents duplicate launcher sessions;
a user-only Unix socket receives stop requests. Startup logs are in
`.cache/app.log`; the bridge does not log typing context. If you manually select
another input source during the session, shutdown preserves that selection.

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

`bun run runtime:download` installs a checksum-pinned upstream llama.cpp b10964
Vulkan release into `.cache/llama-vulkan`. It recognizes both the Intel integrated
GPU and the RTX 4060. The launcher prefers this cached runtime and selects NVIDIA
when detected; `RIWEN_DEVICE` overrides the choice. No system binary is replaced.

Use a recent llama.cpp server with NVIDIA CUDA or Vulkan support. Set
`RIWEN_LLAMA_SERVER=/absolute/path/to/llama-server` before `bun run model:start`
for an isolated runtime. The launcher checks GPU availability; pass `--cpu` for an
explicit CPU baseline. Model download verifies SHA-256 and reuses valid files.
An interrupted `.part` file is rejected: remove it and retry.

The launcher uses 2,048 context tokens, one slot, six CPU threads, thinking disabled,
and port 18080. The bridge's deadline is 1.2 seconds. Slow backends fall back.

## Isolated native runtime and IBus frontend

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
release, extracts them into `.cache/rime-native`, and compiles the local bridge.
No RPM is installed and no system library is replaced. If the matching release is
absent from the Fedora repository, preparation fails rather than mixing versions.

`ibus:prepare` copies compiled static assets from `~/.config/ibus/rime` (or
`$XDG_CONFIG_HOME/ibus/rime`) into `.cache/ibus-profile`. It locates
`pin_cand_filter` before inserting Riwen. Learned user databases are not copied;
the experimental engine learns separately in its own profile. Reprepare only
while the experimental frontend is stopped.

The inspected `aux_code.lua` reassigns generic-for variables, which Lua 5.5 rejects.
Preparation adapts those assignments in the **copied** script. The active profile
is untouched. Real-Rime tests verify the plugin can load LuaSocket and the scheme.

For manual control, run `bun run model:start`, `bun run bridge:start`, and
`bun run ibus:start` in separate terminals after preparation. `ibus:start` only
registers `riwen`; select it with `ibus engine riwen`, and switch back with
`ibus engine rime` before stopping it. The frontend refuses profiles outside
the project's `.cache`. No autostart or persistent GNOME installation is provided.
`bun start` performs these steps for normal use, with automatic cleanup.

`test:ibus` runs a separate daemon on a private D-Bus session and socket, with
isolated XDG paths. It selects Riwen **only on that private bus**. Add `--model` to
use the local Qwen endpoint instead of a deterministic ranker. `rime:demo` also
uses Qwen, but drives the native probe without IBus. Both accept
`RIWEN_MODEL_URL=http://127.0.0.1:PORT/v1/chat/completions`; neither needs a separate
`bridge:start` process because each creates an ephemeral bridge.

## Stock IBus Rime: stage before installation

`bun run stage` generates files in `.cache/rime-stage`. The patch assumes the
inspected schema's filter index 4 is `pin_cand_filter`. Recheck this if the scheme
changes. Staging does not install or redeploy anything.

For the stock IBus Rime path, provide a Lua-enabled librime compatible with IBus and verify
`require('socket')` **inside that Rime process**. Standalone Lua success is not
sufficient. Do not substitute incompatible shared libraries system-wide.

For intentional installation:

1. Back up existing customizations.
2. Copy staged `lua/riwen.lua` into the Rime user directory's `lua/` folder.
3. Merge patch keys into `rime_frost_double_pinyin_flypy.custom.yaml`, preserving
   existing `patch:` entries.
4. Redeploy through the Rime menu and test in a disposable ordinary text field.
5. To remove, remove only Riwen's two engine entries and `riwen/port`, redeploy,
   stop local processes, and optionally delete `lua/riwen.lua`.

## Sources

Context7 was over quota. Upstream documentation and installed IBus GI/C API
introspection were used:

- [librime-lua](https://github.com/hchunhui/librime-lua), including `src/types.cc`.
- [IBus key events](https://github.com/rime/ibus-rime/blob/master/rime_engine.c)
  and [notifications](https://github.com/rime/ibus-rime/blob/master/rime_main.c).
- [Bun UDP](https://bun.com/docs/runtime/networking/udp).
- [Python process ownership](https://docs.python.org/3/library/subprocess.html),
  including `start_new_session`; Context7 was still over quota for the launcher.
- [LuaSocket UDP](https://lunarmodules.github.io/luasocket/udp.html).
- [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
- [Qwen3 model](https://huggingface.co/Qwen/Qwen3-1.7B).
- [Q4_K_M weights](https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF).
