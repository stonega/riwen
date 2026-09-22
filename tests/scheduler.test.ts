import { expect, test } from "bun:test";
import { Scheduler } from "../src/scheduler";

const sample = {
  id: "1",
  context: "我在写",
  input: "igui",
  candidates: ["城市", "程式"],
};
test("rapid requests collapse to the latest context", async () => {
  const calls: string[] = [];
  const result = Promise.withResolvers<number>();
  const scheduler = new Scheduler(
    async (request) => {
      calls.push(request.id);
      return 2;
    },
    { debounceMs: 10, timeoutMs: 1000 },
  );
  try {
    scheduler.submit("a", sample, () => {
      throw new Error("Stale callback");
    });
    scheduler.submit("a", { ...sample, id: "2" }, (best) =>
      result.resolve(best),
    );
    expect(await result.promise).toBe(2);
    expect(calls).toEqual(["2"]);
  } finally {
    scheduler.close();
  }
});
test("cancels active stale work before starting the latest request", async () => {
  const started = Promise.withResolvers<void>();
  const finished = Promise.withResolvers<number>();
  let aborted = false;
  const replies: string[] = [];
  const scheduler = new Scheduler(
    async (request, signal) => {
      if (request.id === "1") {
        started.resolve();
        await new Promise<void>((_resolve, reject) =>
          signal.addEventListener(
            "abort",
            () => {
              aborted = true;
              reject(new Error("aborted"));
            },
            { once: true },
          ),
        );
      }
      return 2;
    },
    { debounceMs: 0, timeoutMs: 1000 },
  );
  try {
    scheduler.submit("a", sample, () => replies.push("old"));
    await started.promise;
    scheduler.submit("a", { ...sample, id: "2" }, (best) => {
      replies.push("new");
      finished.resolve(best);
    });
    expect(await finished.promise).toBe(2);
    expect(aborted).toBe(true);
    expect(replies).toEqual(["new"]);
  } finally {
    scheduler.close();
  }
});
test("timeout and inference errors preserve the native first candidate", async () => {
  for (const timeout of [false, true]) {
    const result = Promise.withResolvers<[number, string]>();
    const scheduler = new Scheduler(
      async (_request, signal) => {
        if (timeout)
          await new Promise<void>((_resolve, reject) => {
            signal.addEventListener(
              "abort",
              () => reject(new Error("timeout")),
              { once: true },
            );
          });
        throw new Error("model unavailable");
      },
      { debounceMs: 0, timeoutMs: 20 },
    );
    try {
      scheduler.submit("a", sample, (best, status) =>
        result.resolve([best, status]),
      );
      expect(await result.promise).toEqual([1, "fallback"]);
    } finally {
      scheduler.close();
    }
  }
});

test("an inference that ignores cancellation cannot block later requests", async () => {
  const stuck = Promise.withResolvers<number>();
  const timedOut = Promise.withResolvers<string>();
  const recovered = Promise.withResolvers<number>();
  const replies: string[] = [];
  const scheduler = new Scheduler(
    (request) => (request.id === "1" ? stuck.promise : Promise.resolve(2)),
    { debounceMs: 0, timeoutMs: 30 },
  );
  try {
    scheduler.submit("a", sample, (_best, status) => {
      replies.push(status);
      timedOut.resolve(status);
    });
    expect(await timedOut.promise).toBe("fallback");
    scheduler.submit("b", { ...sample, id: "2" }, (best) =>
      recovered.resolve(best),
    );
    expect(await recovered.promise).toBe(2);
    stuck.resolve(2);
    await Bun.sleep(0);
    expect(replies).toEqual(["fallback"]);
  } finally {
    scheduler.close();
    stuck.resolve(2);
  }
}, 1000);
