# Riwen

Riwen is a local context-aware candidate-ranking and phrase-correction prototype for IBus Rime,
supporting deployed script/table Rime schemes and a GNOME 51 extension UI. It uses Python for the local inference bridge, launcher and IBus frontend,
Lua for Rime, and a C++ librime bridge. Bun/TypeScript remain developer test tools,
not product runtime dependencies. Fedora RPM installs the backend and GNOME UI. No web app or cloud service is needed.

## Layout

- `src/riwen/`: Python protocol, model client, scheduling, local UDP service, paths and profile preparation.
- `gnome/`: extension panel, preferences, lifecycle controller, and candidate badge.
- `src/native/`: serialized librime C API bridge and command-line probe.
- `src/ibus/`: experimental main-loop IBus frontend using an isolated profile.
- `src/voice/`: focus-bound dictation controller, PipeWire capture and local ASR worker.
- `rime/lua/`: nonblocking Rime processor and filter.
- `tests/`: deterministic TypeScript and Lua tests.
- `scripts/`: development, staging, and benchmark tools.
- `scripts/app.py`: one-command session launcher, ownership, and rollback.
- `scripts/runtime.py`: Python setup, model and bridge commands.
- `packaging/riwen.spec`: RPM with system-installed extension and native bridge.
- `examples/`: runnable requests and benchmark cases.
- `docs/design/`, `docs/implementation/`, `docs/user/`: architecture, setup, usage.
- `postmortem/`: incident notes when relevant.

## Workflow

Read the design and implementation notes before changing behavior. Build a small
end-to-end slice first. Keep functions small, dependencies explicit, and docs
aligned with runnable commands. Use Bun and Biome for TypeScript.

Run `bun run check`, `bun run test:python`, `bun test`, and `bun run test:lua` before finishing changes.
For Lua/native/frontend changes, also run `bun run test:rime` and
`bun run test:ibus` after `bun run rime:prepare`. IBus tests use a private bus;
never substitute the desktop bus. For phrase-correction changes also run
`bun run test:ibus --correction`. Tests must cover stale results, model failures,
focus boundaries, private fields, and selection stability. Model
benchmarks are optional network/model-dependent checks and are not unit tests.
For extension changes also run `bun run test:extension` and validate the packaged
backend on a private bus. For launcher changes also run `bun run test:launcher`; keep startup and restoration
tests on a private bus. `riwen start` is the installed app; `python3 scripts/app.py start` is the checkout
entry point (`bun start` is a developer alias). `bridge:start` runs only the UDP service.
For packaging changes build with `python3 scripts/package-rpm.py` and run
`python3 tests/rpm-package.py`; never install the RPM on the desktop for a test.
For voice changes run `bun run test:voice` and `bun run test:ibus --voice`.
Use fixtures or public WAV samples, never ambient microphone recording, for
automated tests. Do not persist audio/transcript history. Keep recording scoped
to the current non-private field and reject results after focus/reset/cancel.

## Input-method constraints

- Never block the Rime callback on inference, DNS, subprocesses, or file polling.
- Preserve native candidates when the service is absent or a response is invalid.
- Never apply a late ranking immediately before Space/number-key commit.
- Preserve pinned/custom phrases and candidates with different segment ranges.
- Generated corrections must preserve the original candidate and input span;
  reject unrestricted rewrites, invalid characters, and late/stale results.
- Do not log or persist typing context. Keep all inference on loopback.
- Track recent commits only; do not claim this is the application's surrounding text.
- Stage configuration separately. Do not restart IBus, redeploy the user's input
  method, or overwrite their Rime files without an explicit installation request.
- Use git for version control; use gh only when git is insufficient.
- Use CodeGraph for indexed structural exploration, and native search for literals.
  Do not create its index without the user's agreement.
- Fetch current library/API documentation through Context7; if unavailable,
  document the fallback to upstream documentation.

Update docs and runnable examples with feature changes. Keep tests under `tests/`
and automation under `scripts/`. Do not add frameworks without a concrete need.
