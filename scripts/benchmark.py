"""Optional model-only benchmark. No real typing data is recorded."""
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from riwen.model import Model
from riwen.protocol import Request


async def main():
    cases = json.loads((Path(__file__).resolve().parents[1] / "examples/cases.json").read_text())
    rank = Model(os.environ.get("RIWEN_MODEL_URL", "http://127.0.0.1:18080/v1/chat/completions"))
    def request(index, case):
        return Request(str(index + 1), case["context"], case["input"], case["candidates"])
    started = time.monotonic()
    await rank(request(0, cases[0]))
    first = round((time.monotonic() - started) * 1000)
    results = []
    for pass_number in range(3):
        for index, case in enumerate(cases):
            started = time.monotonic()
            result = {"pass": pass_number, "case": index + 1}
            try:
                async with asyncio.timeout(10):
                    best = await rank(request(index, case))
                result.update(selected=case["candidates"][best - 1], correct=case["candidates"][best - 1] == case["expected"])
            except Exception as error:
                result.update(correct=False, error=type(error).__name__)
            result["ms"] = round((time.monotonic() - started) * 1000)
            results.append(result)
    times = sorted(item["ms"] for item in results)
    print(json.dumps({"model": "Qwen3-1.7B Q4_K_M", "timestamp": datetime.now(timezone.utc).isoformat(),
                      "firstRequestMs": first, "correct": sum(item["correct"] for item in results), "total": len(results),
                      "p50Ms": times[math.ceil(len(times) * .5) - 1], "p95Ms": times[math.ceil(len(times) * .95) - 1],
                      "note": "Synthetic model-only benchmark; excludes debounce, Rime/IBus, and real typing. Not an accuracy evaluation.",
                      "results": results}, ensure_ascii=False, indent=2))


asyncio.run(main())
