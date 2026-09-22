import cases from "../examples/cases.json";
import { createRanker } from "../src/model";

const rank = createRanker(
  process.env.RIWEN_MODEL_URL ?? "http://127.0.0.1:18080/v1/chat/completions",
);
// First benchmark request, not necessarily a cold model or shader cache.
const firstStarted = performance.now();
const first = cases[0];
if (!first) throw new Error("No benchmark cases");
await rank({ ...first, id: "1" }, AbortSignal.timeout(30_000));
const firstMs = performance.now() - firstStarted;
const results = [];
for (let pass = 0; pass < 3; pass++) {
  for (const [index, example] of cases.entries()) {
    const started = performance.now();
    try {
      const best = await rank(
        { ...example, id: String(index + 1) },
        AbortSignal.timeout(10_000),
      );
      results.push({
        pass,
        case: index + 1,
        ms: Math.round(performance.now() - started),
        selected: example.candidates[best - 1],
        correct: example.candidates[best - 1] === example.expected,
      });
    } catch (error) {
      results.push({
        pass,
        case: index + 1,
        ms: Math.round(performance.now() - started),
        correct: false,
        error: error instanceof Error ? error.message : "unknown",
      });
    }
  }
}
const times = results.map((r) => r.ms).sort((a, b) => a - b);
console.log(
  JSON.stringify(
    {
      model: "Qwen3-1.7B Q4_K_M",
      timestamp: new Date().toISOString(),
      firstRequestMs: Math.round(firstMs),
      correct: results.filter((r) => r.correct).length,
      total: results.length,
      p50Ms: times[Math.ceil(times.length * 0.5) - 1],
      p95Ms: times[Math.ceil(times.length * 0.95) - 1],
      note: "Synthetic model-only benchmark; excludes 80ms debounce, Rime/IBus, and real typing. Not an accuracy evaluation.",
      results,
    },
    null,
    2,
  ),
);
