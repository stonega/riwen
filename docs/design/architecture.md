# Architecture

Riwen is a local Bun service plus a Rime Lua processor/filter. LuaSocket sends
nonblocking UDP datagrams on loopback. An experimental Python IBus frontend uses a
small C++ bridge to librime for automatic redraws. No inference runs in Rime.

## Flow

1. The filter collects at most eight normal candidates, sends a ranking request
   when eligible, and immediately yields the unchanged candidates.
2. The service debounces for 80 ms and runs one inference at a time. New requests
   replace queued work and cancel obsolete active work from the same socket.
3. Qwen returns a constrained `best` index with thinking disabled.
4. The experimental frontend polls every 40 ms while pending, using a GLib timer
   at idle priority. It changes `riwen_poll` on the main thread; Lua validates the
   response and refreshes Rime's nonconfirmed composition. The frontend then sends
   the new IBus lookup table. Stock IBus Rime uses F8 for this step instead.
5. Missing results preserve native ranking. F8 can retry after expiry.

When a valid choice is applied, Lua exposes its text as `riwen_choice`. The native
bridge passes it as `qwen_choice`; the frontend appends `〔Qwen〕` to the matching
menu entry only. Candidate objects and committed text are unchanged. A change to
this metadata triggers redraw even when Qwen agrees with the original first
candidate. Reset, commit, and invalidated requests clear the metadata.

Service deadline: 1,200 ms including queue and debounce. Lua expiry: 2 seconds.
The scheduler bounds its own wait even if a ranker ignores cancellation; a stuck
transport cannot retain the queue indefinitely. The HTTP adapter explicitly
settles aborted requests, and Lua records fallback when no choice was available.
Dropped packets are harmless; F8 retries after expiry. Nothing is cached on disk.
Model KV/prompt caching remains in the model process.

## Long-phrase correction

When the native first candidate covers the entire input and contains 6–24 basic
CJK characters, Riwen can request one new correction instead of ranking the
existing eight. This path does not require prior committed context. The remaining
native candidates may cover shorter spans, but custom/high-priority first choices,
auxiliary codes, and a moved composition caret still bypass assistance.

`R2` carries context, double-pinyin input, expanded preedit pinyin, and the original
first candidate. Qwen receives the original phrase, raw keys, and prior context,
with two unrelated correction demonstrations. Directly presenting typo-containing
expanded pinyin as a target made this small model preserve malformed phrases, so
the current prompt does not use that field as a pronunciation constraint.

The model returns a JSON `text` field. Both service and Lua enforce same-length
CJK-only output with at most three replacements, affecting no more than half the
characters. Unchanged, empty, or invalid outputs add nothing. These are structural
guards, not proof of grammatical correctness or exact phonetic alignment.

Correction requests debounce for 240 ms and have a 3-second service deadline;
Lua and the frontend wait up to 4 seconds. They share the serial inference queue
and stale-request cancellation with ranking. A valid correction becomes a new
Rime candidate with the original span, quality, and preedit; original candidates
remain available and later pin filters retain precedence. The existing Qwen badge,
navigation freeze, focus reset, and ordinary commit behavior apply to corrections.

## Stability

Space, Return, numbers, and navigation never apply pending results inside their
key handlers. Idle callbacks may visibly update the menu before later key events;
they are not synchronized to physical screen presentation. Candidate navigation
freezes automatic application. Replies must
match request ID, input, context, and original candidates, with an index in range.
Original candidate objects and candidates beyond the first eight are preserved.

The first eight must be script candidates (`phrase`, `user_phrase`, `sentence`),
have matching ranges, and quality below 90. Mixed English/custom lists, different
segment spans, auxiliary codes, and input with a moved cursor bypass ranking.
This deliberately limits prototype coverage. The patch inserts before
`pin_cand_filter` so explicit pins are applied afterward.

## Context

Recent Rime commits are capped at 768 UTF-8 bytes. Edits, navigation, common control
shortcuts, F9, and 30 seconds of inactivity clear context. This is **not** actual
application surrounding text. The experimental frontend clears context and
composition on focus loss, resets context on content-type changes, and bypasses
PASSWORD, PIN, and PRIVATE fields. Stock IBus Rime's Lua extension lacks these
frontend hooks; use F9 after focus changes there. Mouse edits and pastes within a
field can still leave incomplete context. Neither path consumes surrounding text.

## Protocol

Request: `R1\t<id>\t<context-hex>\t<input-hex>\t<candidate1-hex>\t...`

Reply: `R1\t<id>\t<1-based-best>\t<ok|fallback>`.

Correction request: `R2\t<id>\t<context-hex>\t<input-hex>\t<pinyin-hex>\t<original-hex>`.
Correction reply: `R2\t<id>\t<correction-hex>\t<ok|fallback>` (empty text means no addition).

Hex-encoded UTF-8 avoids another Lua dependency. Both ends bind loopback; fields
are bounded and validated. Model URLs must use HTTP on literal `127.0.0.1`;
redirects are rejected. Both proxy-bypass environment variables exempt loopback.
Typing is never logged or persisted by the bridge. Same-host processes are not an
authenticated trust boundary; production should use a user-owned Unix socket.

## Frontend boundary

IBus Rime updates its menu after processing keys. Its notification handler handles
deployment, not arbitrary async menu refreshes. Lua refresh from a worker is neither
thread-safe nor sufficient to redraw IBus. Stock IBus therefore retains explicit
F8. `src/ibus/engine.py` owns Rime sessions through `src/native/rime_bridge.cpp`;
all ctypes calls, key handling, property notifications, and redraws are serialized
on one main loop. Each session has its own UDP socket and increasing request IDs.
Focus/reset drops pending requests and stops timers; teardown destroys sessions
before librime finalization. The native bridge is not a general thread-safe API.

The separate `riwen` frontend registers transiently and never selects itself.
It loads a matching Lua plugin from `.cache` and an isolated copy of compiled
dictionary assets, without importing learned user databases. It is a test frontend,
not a complete replacement for stock IBus Rime's settings and UI integration.

`scripts/app.py` supplies the normal `bun start` entry point. It prepares the
isolated runtime/profile, starts or reuses Qwen, starts the UDP bridge and frontend,
then selects Riwen through IBus. All services must report readiness first. Each
owned subprocess has its own process group; failure, signals, and the stop socket
all restore the previous engine before group teardown. The previous source is
restored only if Riwen remains selected, preserving manual source changes.
Preparation and inference remain outside Rime callbacks. The default model port
is probed without proxies or redirects; an unresponsive process is never killed.

## Validation

Lua fixtures cover protocol and selection behavior. Native tests additionally
exercise real librime iterator semantics, 小鹤 dictionaries, and UDP round trips.
Private D-Bus/IBus tests observe actual lookup-table updates while idle and verify
focus boundaries and sensitive-field bypass. `test:ibus --model` replaces the
deterministic ranker with Qwen. These tests do not prove GNOME's visual rendering
or measure typing accuracy across ordinary applications.

Next-stage criteria: real top-1 improvement, fewer manual selections, bounded p95
latency, and no menu movement after selection starts.
