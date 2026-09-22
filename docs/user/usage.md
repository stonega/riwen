# Using Riwen

## GNOME extension

Install the Riwen RPM using DNF, sign out/back in, then enable **Riwen — Local
Qwen for Rime** in GNOME Extensions. Installing the RPM does not enable or start
Riwen. Once enabled, click the speech-bubble icon with two text strokes in the top
bar to open Riwen's menu. The menu opens centered beneath the icon, shifting inward
near a screen edge. It shows preparation/model status and reports **Ready** when
you can type. First use downloads about 1.3 GB. The optional Python extension
ZIP remains available; see [setup](../implementation/setup.md).

- **Qwen assistance:** start or stop; off restores the previous input method.
- **Rime scheme:** choose from your deployed Rime schemes, or follow the last-used
  scheme/default list. Then click **Restart to apply settings**.
- **Settings:** automatic enablement, colored badges, phonetic phrase correction,
  CPU mode for machines without a Vulkan GPU, and an optional Rime profile folder.
  Scheme, profile, CPU, and correction changes take effect on restart.

The selected scheme's native candidate page size and selection labels are used.
Ranking supports ordinary script and table candidates, with each scheme's
alphabet. Long-phrase correction is enabled for script-translator schemes only;
shape/table input keeps candidate ranking. Custom/high-priority candidates remain
protected. Custom third-party Lua filters may need additional compatibility work.

The packaged target is GNOME 51 on Fedora x86_64. The RPM installs the Python
backend and prebuilt native bridge, and declares its system dependencies. It does
not need Bun or Node.js. You must already have a deployed Rime scheme. Missing
configuration or model setup failures appear in the panel.

## Voice input

Voice input is enabled by default in the complete Riwen app and works with any
selected Rime scheme. It uses local CPU inference with Qwen3-ASR-0.6B, migrated
from ibus-voice. The standalone Lua filter in stock IBus Rime does not include it.

1. Open the Riwen panel and select **Prepare voice model**. Wait for **Voice ready**.
   First use prepares an independent Python runtime and downloads about 879 MB;
   existing ibus-voice model files are reused automatically.
2. Focus an ordinary text field, finish any existing Rime composition, and press
   **F10**. The input popup shows **Listening**; speak into the default microphone.
3. Press **F10** again. When recognition finishes, the text is inserted into the
   same field. Recording stops automatically at 60 seconds. **Esc** cancels.

From `riwen start`, the first F10 prepares the model; press F10 again once ready.
You can also run `riwen voice-prepare` and check
`riwen voice-status` from another terminal.

Switching fields, resetting input, or typing another key cancels dictation. Late
results are discarded. Password/PIN/private fields bypass voice when the app
reports them correctly. The panel's **Cancel dictation** also cancels a pending
job. Opening a menu can change field focus, so start recording with F10 in the
target field. Ctrl+Space keeps its usual input-method behavior.

Recognition runs after recording, not as live partial text. Audio stays in memory
and transcripts are delivered through IBus; neither is saved as history or sent
to a cloud service. As with typing, applications receive the committed text.
The voice model stays loaded until Riwen stops. Turn off **Local voice input** in
settings and restart Riwen to release it and stop capturing F10; terminal users
can start with `RIWEN_VOICE=0 riwen start`.

If recording fails, check the desktop's default PipeWire microphone, mute switch,
permissions and `pw-record` installation. If setup fails, retry **Prepare voice
model** after resolving the reported download/runtime error. Recognition times
out after 60 seconds; use shorter utterances on slower CPUs.

## Terminal development and 小鹤 examples

`python3 scripts/app.py start` is available from a checkout. Stop it before enabling a separate
extension-managed Riwen session. The examples below use 小鹤双拼; use your own
scheme's spelling otherwise.

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
riwen stop
```

Keep the terminal open only when using `riwen start`. The installed extension owns
its own background session and needs no terminal. Its **Enable Riwen** preference
persists across logins. Disabling the extension stops processes it started and
restores the previous input method.

## Colored Qwen badge

The extension displays a small purple pill with white **Qwen** lettering after
assisted candidates. It is presentation only; committed text contains just the
candidate. Toggle **Colored Qwen badges** in settings to use the plain `〔Qwen〕`
marker instead. This setting takes effect immediately.

After updating the extension, sign out and back in to load its new code. GNOME 51
cannot reload a newly installed extension in the current Shell session. The
extension is named **Riwen — Local Qwen for Rime**; its stable UUID remains
`riwen-badge@riwen`. Check the GNOME Extensions app if the panel menu is absent.

## Keys

- **Space / numbers:** commit the displayed candidate as usual.
- **F9:** forget recent context and pending suggestions.
- **F8:** apply a ready suggestion manually, or retry an expired request.
- **F10:** prepare voice on first use; then start/finish dictation.
- **Esc during dictation:** cancel and discard speech.
- Candidate navigation freezes automatic reordering for that request.

Riwen tracks recent commits, not the surrounding document. It clears context on
focus changes and skips password/PIN/private fields when applications report them
correctly. Use F9 after mouse edits or pastes. Pinned phrases keep their priority.
This is limited phrase correction, not unrestricted sentence completion.

## If startup fails

The terminal gives a short error and points to the launcher log, normally
`$XDG_RUNTIME_DIR/riwen/app.log` for RPM installs or `.cache/app.log` in a checkout. Riwen restores the previous input method when possible and cleans up
its own processes. A healthy existing Qwen server is reused; an unresponsive
server is left alone while Riwen starts its own instance on another local port.
An explicitly configured `RIWEN_MODEL_URL` must be healthy or startup stops.

Run `riwen start` again after resolving a reported missing system dependency. See
[advanced setup](../implementation/setup.md) for requirements and individual
service commands. Emergency return to stock Rime: `ibus engine rime`.
