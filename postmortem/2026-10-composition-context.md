# Composition edits discarded ranking context

The reported menu showed `chu fa` with `出发 〔Qwen〕` even though the preceding
sentence ended in `且不经常`. The badge confirms that a ranking was applied;
it does not establish which context the running session sent.

A disposable real-Rime profile reproduced a confirmed failure: after committing
`选词很不准确，且不经常`, typing `iufx`, Backspace, then `a` sent a request for
`iufa` with empty context. The processor treated spelling edits like application
edits and reset the entire commit history. With the existing prompt and the
running Qwen3.5-4B, the full-context request chose `触发`, while the empty-context
request chose `出发`. This demonstrates a cause of the symptom, not proof of the
exact keystroke sequence preceding the screenshot.

Plain composition edits now invalidate pending/applied choices without discarding
preceding commits. Application edits, shortcuts, focus/privacy changes, explicit
reset and inactivity retain their history-clearing behavior. Edits at composition
edges that could reach the application also clear history. Regression checks
reject pre-edit replies and cover both composition and document edits.

Two separate coverage limits also contributed to apparent inactivity. Script
schemes required four keys, excluding many single-character inputs, and ranking
had a 1.2-second end-to-end budget even with the newer 4B model. Scripts now accept
two-key inputs (single initials still bypass assistance). Ranking has a bounded
three-second service deadline and four-second Lua/frontend expiry. Correction
deadlines are unchanged. Slow-reply tests cover application after two seconds,
expiry rejection, native candidate preservation, navigation and commit stability.

The fixed example is in `examples/cases.json` and `examples/request.py --trigger`.
`bun run test:ibus --trigger` exercises spelling repair, context retention and
automatic badge/commit on a private IBus bus; add `--model` to use local Qwen.
No desktop input-method configuration is changed by these tests.
