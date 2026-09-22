import type { Ranker } from "./model";
import type { RankRequest } from "./protocol";

type Job<Result> = {
  peer: string;
  request: RankRequest;
  readyAt: number;
  expiresAt: number;
  reply: (best: Result | 1, status: "ok" | "fallback") => void;
};

/** One inference at a time, with at most the latest pending request per peer. */
export class Scheduler<Result = number> {
  private pending = new Map<string, Job<Result>>();
  private active?: { job: Job<Result>; controller: AbortController };
  private timer?: ReturnType<typeof setTimeout>;
  private closed = false;

  constructor(
    private rank: Ranker<Result>,
    private options: {
      debounceMs: number;
      timeoutMs: number;
      correctionTimeoutMs?: number;
      correctionDebounceMs?: number;
    } = { debounceMs: 80, timeoutMs: 1200 },
  ) {}

  submit(peer: string, request: RankRequest, reply: Job<Result>["reply"]) {
    if (this.closed) return;
    if (this.active?.job.peer === peer) this.active.controller.abort();
    if (!this.pending.has(peer) && this.pending.size >= 32) {
      reply(1, "fallback");
      return;
    }
    const now = performance.now();
    const correction = request.pinyin !== undefined;
    this.pending.set(peer, {
      peer,
      request,
      reply,
      readyAt:
        now +
        (correction
          ? (this.options.correctionDebounceMs ?? 240)
          : this.options.debounceMs),
      expiresAt:
        now +
        (correction
          ? (this.options.correctionTimeoutMs ?? 3000)
          : this.options.timeoutMs),
    });
    this.pump();
  }

  close() {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.pending.clear();
    this.active?.controller.abort();
  }

  private pump() {
    if (this.closed || this.active) return;
    if (this.timer) clearTimeout(this.timer);
    const job = [...this.pending.values()].sort(
      (a, b) => a.readyAt - b.readyAt,
    )[0];
    if (!job) return;
    const wait = job.readyAt - performance.now();
    if (wait > 0) {
      this.timer = setTimeout(() => this.pump(), wait);
      return;
    }
    this.pending.delete(job.peer);
    if (job.expiresAt <= performance.now()) {
      job.reply(1, "fallback");
      this.pump();
      return;
    }
    const controller = new AbortController();
    this.active = { job, controller };
    const timeout = setTimeout(
      () => controller.abort(),
      job.expiresAt - performance.now(),
    );
    void this.run(job, controller).finally(() => {
      clearTimeout(timeout);
      this.active = undefined;
      this.pump();
    });
  }

  private async run(job: Job<Result>, controller: AbortController) {
    const interrupted = Promise.withResolvers<never>();
    const onAbort = () => interrupted.reject(controller.signal.reason);
    controller.signal.addEventListener("abort", onAbort, { once: true });
    try {
      // Abort is advisory to the ranker. Bound our own wait even if a transport
      // never settles its promise after cancellation, so the queue can recover.
      if (controller.signal.aborted) onAbort();
      const best = await Promise.race([
        this.rank(job.request, controller.signal),
        interrupted.promise,
      ]);
      if (!controller.signal.aborted && !this.closed) job.reply(best, "ok");
      else if (!this.closed && !this.pending.has(job.peer))
        job.reply(1, "fallback");
    } catch {
      if (!this.closed && !this.pending.has(job.peer)) job.reply(1, "fallback");
    } finally {
      controller.signal.removeEventListener("abort", onAbort);
    }
  }
}
