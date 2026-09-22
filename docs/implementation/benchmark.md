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
Run `bun run benchmark` with the model running to reproduce. Timings include local
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
