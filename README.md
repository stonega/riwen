# Riwen

Local Qwen-powered 候选词 ranking and phrase correction for **IBus + 雾凇小鹤双拼**.

## Start

From this directory:

```sh
bun start
```

Riwen prepares its isolated profile, downloads the model if needed (about 1.3 GB),
starts the services, and selects the experimental input method. Wait for
**“Riwen is ready”**, then type normally. On your inspected Fedora setup, no manual
configuration or extra terminals are needed.

Type `woxpleyige`, Space, then `igui` and pause: after `我写了一个`, Qwen can promote
`程式`. You still choose when to commit with Space or a number.

Long phrases can also gain a corrected candidate. For example, `veuizfmhhvui`
can add **这是怎么回事 〔Qwen〕** above the original **这是怎忙会是**.

**Stop:** press **Ctrl+C**, or run `bun run stop` from another terminal. Riwen
restores the previous input method and stops the processes it started. Your
existing Rime configuration and learned dictionaries stay in place.

This is an experimental session, not a persistent GNOME input-source installation.
It uses recent committed text and can suggest limited corrections to long phrases.
It never commits automatically. Use **F9** to forget context after mouse edits or pastes.

[Usage](docs/user/usage.md) · [System requirements / advanced setup](docs/implementation/setup.md)
· [Architecture](docs/design/architecture.md) · [Measured results](docs/implementation/benchmark.md)

## Development

```sh
bun install
bun run check
bun test
bun run test:lua
bun run rime:prepare
bun run test:rime
bun run test:ibus
bun run test:ibus --correction
bun run test:launcher
```

Integration checks use private IBus sessions and leave the desktop input source
alone. The launcher test covers startup, automatic selection, candidate updates,
duplicate starts, and restoring the previous engine on stop. GNOME's visual
rendering still needs an interactive trial.

For separate services, use `bun run model:start`, `bun run bridge:start`, and
`bun run ibus:start`; see the advanced setup notes. Stock IBus Rime can use the
staged Lua extension with **F8** instead of the experimental frontend.
