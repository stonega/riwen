# Ranking service stopped answering

The desktop had selected Riwen, the badge code was present in its profile, and
the model health endpoint was healthy. Synthetic requests sent to the running
UDP service received no reply within three seconds. A fresh service using the
same model returned a choice in about 939 ms; a real Rime demo completed in
1,044 ms. Restarting only the test service did not require changing the desktop.

The scheduler had an unbounded wait: its deadline only aborted an AbortSignal,
then waited for the ranker's promise to settle before releasing the queue. A
transport promise that never settled after abort would block every later request.
A regression test with a noncooperative ranker failed on the old implementation.
This is a confirmed failure mechanism; the exact internal state of the previously
running process was not instrumented, so it is not proof of its transport cause.

The scheduler now races its own wait against cancellation, suppresses late
results, returns fallback, and releases the queue. The HTTP adapter explicitly
rejects and destroys its request on abort. An incomplete-response test checks
client recovery. Lua records fallback instead of leaving its status pending.
No typing context is logged. Existing running processes require a restart to load
the correction.
