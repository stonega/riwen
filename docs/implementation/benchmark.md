# Initial model benchmark — 2026-09-22

Qwen3-1.7B Q4_K_M, llama.cpp b10964, Vulkan1 / NVIDIA RTX 4060 Laptop,
2,048-token context, one slot, thinking off, constrained JSON candidate index.

| Measurement | Result |
| --- | --- |
| Expected choices | 8 of 8 synthetic cases, repeated successfully 3 times |
| Warm median request | 442 ms |
| Warm p95 request | 516 ms |
| First benchmark request | 698 ms (model already loaded) |
| GPU memory observed | About 1.4 GiB |

[Raw results](benchmarks/qwen3-1.7b-vulkan.json) and [cases](../../examples/cases.json).
Run `python3 scripts/benchmark.py` with the model running to reproduce. Timings include local
HTTP and model execution, excluding the bridge's 80 ms debounce, Rime, and IBus.
The sample set was used while refining the prompt; it is **not** a held-out accuracy
test. This benchmark used no real typing corpus or actual dictionary candidates.

The first prompt always selected candidate 1. Reframing the task as filling a
sentence blank, with numbered candidates and without an instruction to prefer
candidate 1 under uncertainty, resolved that on these examples. The initial CPU
run took roughly 3 seconds per request; its different prompt/runtime means this is
not a controlled CPU-versus-GPU comparison.

The full headless Lua extension → UDP service → Qwen → Lua F8 demo also passed:
`城市, 程式, 诚实` became `程式, 城市, 诚实` after context `我用Python写了一个`.
The headless fixture alone does not prove IBus integration.

## Real Rime and private IBus validation — 2026-09-22

The native bridge loads Fedora's matching Lua plugin from an extracted RPM.
`rime:demo` now uses the actual 小鹤 dictionary, LuaSocket, bridge, and Qwen with
automatic property polling. With context `我写了一个`, input `igui` produced:

```text
Before: 城市, 🏙, 诚实, 成事, 程式, 乘势, 程氏, 乘时
After:  程式, 城市, 🏙, 诚实, 成事, 乘势, 程氏, 乘时
Space commits: 程式
```

The successful native run took 998 ms from the initial menu to the updated menu,
including debounce and polling. The first attempt retained native order and
failed the expected-choice check; its cause was not instrumented. A separate
model-only request with a slightly different candidate list took 1,640 ms, beyond
the bridge's 1,200 ms deadline. These are individual observations, not a new p95
benchmark, and show that the earlier synthetic timings do not guarantee latency.

`test:ibus --model` passed the real-Qwen idle lookup-table update, focus reset, and
password/PIN/private-field bypass checks on a private IBus bus. This used a second
local model instance on port 18081 because the existing server on 18080 failed its
health check; that existing process was left alone. The validation instance was
stopped afterward. The user's desktop engine remained `rime`.

Next validation is interactive GNOME rendering and normal typing across apps,
followed by a larger held-out corpus of real candidate lists. No live desktop
input source has been installed or switched during these checks.

## Output-size experiment and correction validation — 2026-09-22

On the user's running Vulkan Qwen3-1.7B instance, compared the eight existing
synthetic cases plus the real-dictionary `我写了一个` case, twice each. Request
order alternated between formats. These are warm model-only measurements on a
shared desktop, not end-to-end latency guarantees or held-out accuracy results.

| Format | Expected choices | Median | p95 |
| --- | --- | --- | --- |
| Existing JSON object (integer comparison) | 18/18 | 387 ms | 433 ms |
| Single integer | 12/18 | 152 ms | 172 ms |
| Existing JSON object (array comparison) | 18/18 | 391 ms | 453 ms |
| Single-item JSON array | 6/18 | 251 ms | 329 ms |

[Raw comparison](benchmarks/output-format-comparison.json). The shorter formats
were rejected because they lost correctness on this small sample; normal ranking
keeps the JSON object. Changing only the output format is not a safe speedup here.

The correction prompt uses two unrelated demonstrations (`泥再干伸么呢` and
`我门去吃晚犯`), and receives original text plus double-pinyin keys and context.
With `你好我写` as context, Qwen changed `这是怎忙会是` to `这是怎么回事` in
659 ms; without context, the same correction took 369 ms. It left
`今天天气非常好` unchanged in 389 ms. These are individual observed requests,
not a broad grammar benchmark. Early prompt variants copied the malformed input;
the tested phrasing is recorded in `createCorrector`.

The actual Qwen → service → Lua → private IBus correction test also passed,
including the visible badge, original-candidate preservation, and clean commit.
Run `RIWEN_MODEL_URL=http://127.0.0.1:PORT/v1/chat/completions bun run test:ibus --model --correction`
against a healthy local model to repeat that path.

Historical timings above predate the Python bridge migration; rerun the Python benchmark before making performance comparisons.

## Qwen3.5 correction comparison — 2026-09-23

The reported `nihcveuizfmohvui` example reproduces the native candidate
`你好这是怎抹灰是` with preedit `ni hao zhe shi zen mo hui shi`. It already
triggers a correction request. Qwen3-1.7B returned `你好，这是怎么抹灰的`, which
the existing length/character guards rejected. Relaxing those guards would allow
an incorrect rewrite; the trigger range was not the problem in this case.

Compared Qwen3.5-4B and Qwen3.5-2B, both Q4_K_M, on Intel Arc (MTL) Vulkan0,
llama.cpp b10964, 2,048-token context, one slot, six threads, thinking disabled.
NVIDIA was not available during these runs. Both used the existing correction
prompt and a new exact-length CJK output schema that prevents punctuation and
added characters during generation. The independent Python/Lua guards still apply.

| Model | Download | Expected output | Warm median | Warm p95 |
| --- | --- | --- | --- | --- |
| Qwen3.5-4B | 2.74 GB | 36/36 | 2,736 ms | 3,122 ms |
| Qwen3.5-2B | 1.28 GB | 24/36 | 1,449 ms | 1,686 ms |

These are 12 fixed examples repeated three times, including four correct-sentence
controls. They were used during investigation and are not held-out accuracy
results. Runs were sequential on shared desktop hardware; latency excludes
debounce, Rime/IBus and cold loading. Initial cold requests can still time out.
The 4B result for the reported case was `你好这是怎么回事`; 2B repeatedly
returned the incorrect `你好这是怎么抹灰`. The 2B model also changed `问题`
to `题目` and `文件` to `微信` in other cases. It remains an explicit option;
4B is the default. Both preserved the legitimate sentence `我们正在给墙抹灰`.

The correction service deadline is now five seconds with a six-second Lua/IBus
expiry, accommodating measured 4B latency on integrated graphics. Ranking retains
its then-current 1.2-second deadline. On slower devices either operation may fall back to native
candidates. Navigation, commit and focus boundaries still reject late corrections.
The 4B screenshot example passed the actual model → Python → Lua → private IBus
path, including original-candidate preservation and a clean commit.

[Raw comparison](benchmarks/qwen35-correction.json) and
[fixed examples](../../examples/correction-cases.json). Reproduce with:

```sh
# Set the server URL and model ID to match the instance you started.
RIWEN_MODEL=qwen3.5-4b RIWEN_MODEL_URL=http://127.0.0.1:18083/v1/chat/completions python3 scripts/benchmark-correction.py
RIWEN_MODEL=qwen3.5-2b RIWEN_MODEL_URL=http://127.0.0.1:18084/v1/chat/completions python3 scripts/benchmark-correction.py
```

## Composition context and short-input ranking — 2026-10-23

With the running Qwen3.5-4B Q4_K_M server (llama.cpp b10964, Vulkan1 / RTX 4060,
2,048-token context, one slot), the existing eight ranking cases plus four
`iufa` cases selected the expected candidate in 36/36 requests over three passes.
Warm median was 607 ms and p95 was 740 ms; the first request took 987 ms.
The reported `选词很不准确，且不经常` prefix chose `触发` in all three passes
(545, 561 and 629 ms). The same model with no preceding context chose `出发` in
a separate diagnostic request. No ranking prompt change was needed for this fix.

These are fixed development examples, not held-out accuracy results. Timings
exclude queueing/debounce, Rime and IBus, and used a shared desktop server.
The three-second ranking deadline and four-second Lua/frontend expiry allow
more headroom than the old 1.2-second deadline; they do not guarantee a result.

The real-model private IBus test passed the corrected-spelling flow, automatic
`触发` badge, clean commit, focus reset and sensitive-field bypass. Its first run,
concurrent with other integration suites, failed to observe the expected badge;
an isolated native model probe and subsequent private IBus runs passed. The cause
of that initial failure was not established. Deterministic coverage separately
checks retained context, a 2.1-second reply, expiry and selection stability.

[Raw results](benchmarks/qwen35-ranking-context.json). Reproduce against a healthy
local server with:

```sh
RIWEN_MODEL_URL=http://127.0.0.1:PORT/v1/chat/completions python3 scripts/benchmark.py
RIWEN_MODEL_URL=http://127.0.0.1:PORT/v1/chat/completions bun run test:ibus --model --trigger
```
