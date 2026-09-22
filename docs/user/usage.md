# Using Riwen

Run from the project directory:

```sh
bun start
```

Wait for **“Riwen is ready”**, then type in your usual text editor. First use may
need a 1.3 GB model download. Later starts reuse downloaded files. Riwen handles
preparation, model startup, the ranking service, and selecting the input method.

Try `woxpleyige`, Space, then `igui` and pause. With `我写了一个` as context, Qwen
should promote `程式`. Press Space to commit the displayed first candidate.
The chosen word shows a small badge, like **程式 〔Qwen〕**. The badge also appears
when Qwen agrees with the original first candidate. It is only shown in the
candidate menu; committed text contains just the word.
Suggestions may time out or be wrong; normal candidates remain available.

For a long phrase with apparent typos, Riwen can add a new correction. Try
`veuizfmhhvui` and pause: **这是怎忙会是** can gain **这是怎么回事 〔Qwen〕**
as the first candidate. The original remains selectable. This also works without
previously committed context. If you commit immediately or begin navigating the
menu, a late correction cannot change that selection.

Corrections currently cover full phrases of 6–24 Chinese characters, keep the
same length, and change at most three characters (and no more than half the
phrase). They may fix near-sound typing errors; exact pronunciation is not
guaranteed. Already-correct phrases that the model returns unchanged get no new
candidate or badge. Corrections start after a short typing pause and can take
longer than ranking existing words.

Press **Ctrl+C** to stop and restore your previous input method. Alternatively:

```sh
bun run stop
```

Keep the terminal open while using Riwen. There is no autostart or persistent
GNOME installation. If GNOME reselects another source when you change windows,
that desktop integration still needs an interactive pass.

## Keys

- **Space / numbers:** commit the displayed candidate as usual.
- **F9:** forget recent context and pending suggestions.
- **F8:** apply a ready suggestion manually, or retry an expired request.
- Candidate navigation freezes automatic reordering for that request.

Riwen tracks recent commits, not the surrounding document. It clears context on
focus changes and skips password/PIN/private fields when applications report them
correctly. Use F9 after mouse edits or pastes. Pinned phrases keep their priority.
This is limited phrase correction, not unrestricted sentence completion.

## If startup fails

The terminal gives a short error and points to `.cache/app.log` for startup
information. Riwen restores the previous input method when possible and cleans up
its own processes. A healthy existing Qwen server is reused; an unresponsive
server is left alone while Riwen starts its own instance on another local port.
An explicitly configured `RIWEN_MODEL_URL` must be healthy or startup stops.

Run `bun start` again after resolving a reported missing system dependency. See
[advanced setup](../implementation/setup.md) for requirements and individual
service commands. Emergency return to stock Rime: `ibus engine rime`.
