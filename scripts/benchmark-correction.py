"""Optional local-model check using fixed examples, never captured typing history."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from riwen.model import Model
from riwen.models import selected_model
from riwen.protocol import Request, encode_request


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passes", type=int, default=3)
    args = parser.parse_args()
    if args.passes < 1:
        parser.error("--passes must be positive")
    cases = json.loads((PROJECT / "examples/correction-cases.json").read_text())
    model_name = selected_model()
    correct = Model(os.environ.get("RIWEN_MODEL_URL", "http://127.0.0.1:18080/v1/chat/completions"), model_name)
    results = []
    for repeat in range(args.passes):
        for index, case in enumerate(cases):
            request = Request(str(index + 1), "", case["input"], [case["original"]], case["pinyin"])
            encode_request(request)
            result = {"pass": repeat + 1, "case": index + 1}
            started = time.monotonic()
            try:
                # Match the service's 5-second deadline minus its debounce.
                async with asyncio.timeout(4.76):
                    text = await correct(request)
                result.update(text=text or case["original"], suggestion=bool(text))
            except Exception as error:
                result.update(text=case["original"], suggestion=False, error=type(error).__name__)
            result.update(correct=result["text"] == case["expected"], ms=round((time.monotonic() - started) * 1000))
            results.append(result)
    times = sorted(item["ms"] for item in results)
    print(json.dumps({"model": model_name, "correct": sum(item["correct"] for item in results),
                      "errors": sum("error" in item for item in results),
                      "total": len(results), "p50Ms": times[math.ceil(len(times) * .5) - 1],
                      "p95Ms": times[math.ceil(len(times) * .95) - 1],
                      "note": "Fixed regression examples, not a held-out accuracy evaluation. Model-only latency; no real typing recorded.",
                      "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
