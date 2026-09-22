# Riwen

Riwen is a local context-aware candidate-ranking and phrase-correction prototype for IBus Rime,
initially targeting 雾凇拼音 · 小鹤双拼. It uses Bun/TypeScript for a local
inference bridge and Lua for the Rime extension, plus an experimental Python IBus
frontend and C++ librime bridge. No web app or cloud service is needed.

## Layout

- `src/`: protocol, model client, scheduling, and local UDP service.
- `src/native/`: serialized librime C API bridge and command-line probe.
- `src/ibus/`: experimental main-loop IBus frontend using an isolated profile.
- `rime/lua/`: nonblocking Rime processor and filter.
- `tests/`: deterministic TypeScript and Lua tests.
- `scripts/`: development, staging, and benchmark tools.
- `scripts/app.py`: one-command session launcher, ownership, and rollback.
- `examples/`: runnable requests and benchmark cases.
- `docs/design/`, `docs/implementation/`, `docs/user/`: architecture, setup, usage.
- `postmortem/`: incident notes when relevant.

## Workflow

Read the design and implementation notes before changing behavior. Build a small
end-to-end slice first. Keep functions small, dependencies explicit, and docs
aligned with runnable commands. Use Bun and Biome for TypeScript.

Run `bun run check`, `bun test`, and `bun run test:lua` before finishing changes.
For Lua/native/frontend changes, also run `bun run test:rime` and
`bun run test:ibus` after `bun run rime:prepare`. IBus tests use a private bus;
never substitute the desktop bus. For phrase-correction changes also run
`bun run test:ibus --correction`. Tests must cover stale results, model failures,
focus boundaries, private fields, and selection stability. Model
benchmarks are optional network/model-dependent checks and are not unit tests.
For launcher changes also run `bun run test:launcher`; keep startup and restoration
tests on a private bus. `bun start` is the user-facing app; `bridge:start` runs only
the UDP service.

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
