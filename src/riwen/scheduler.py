"""Serial inference with per-peer replacement and end-to-end deadlines."""
import asyncio
from dataclasses import dataclass


@dataclass
class Job:
    peer: object
    request: object
    reply: object
    ready: float
    expires: float


def consume(task):
    if not task.cancelled():
        task.exception()


class Scheduler:
    def __init__(self, rank, debounce=0.08, timeout=1.2, correction_debounce=0.24, correction_timeout=3):
        self.rank = rank
        self.debounce, self.timeout = debounce, timeout
        self.correction_debounce, self.correction_timeout = correction_debounce, correction_timeout
        self.pending = {}
        self.active = None
        self.interrupted = None
        self.timer = None
        self.runner = None
        self.closed = False

    def submit(self, peer, request, reply):
        if self.closed:
            return
        if self.active and self.active.peer == peer:
            self.interrupted.set()
        if peer not in self.pending and len(self.pending) >= 32:
            reply(1, "fallback")
            return
        now = asyncio.get_running_loop().time()
        correction = request.pinyin is not None
        self.pending[peer] = Job(peer, request, reply,
                                 now + (self.correction_debounce if correction else self.debounce),
                                 now + (self.correction_timeout if correction else self.timeout))
        self.pump()

    def pump(self):
        if self.closed or self.active:
            return
        if self.timer:
            self.timer.cancel()
            self.timer = None
        loop = asyncio.get_running_loop()
        while self.pending:
            job = min(self.pending.values(), key=lambda item: item.ready)
            if job.ready > loop.time():
                self.timer = loop.call_at(job.ready, self.pump)
                return
            del self.pending[job.peer]
            if job.expires <= loop.time():
                job.reply(1, "fallback")
                continue
            self.active = job
            self.interrupted = asyncio.Event()
            self.runner = asyncio.create_task(self.run(job, self.interrupted))
            return

    async def run(self, job, interrupted):
        inference = asyncio.create_task(self.rank(job.request))
        inference.add_done_callback(consume)
        abort = asyncio.create_task(interrupted.wait())
        try:
            done, _ = await asyncio.wait((inference, abort),
                                         timeout=max(0, job.expires - asyncio.get_running_loop().time()),
                                         return_when=asyncio.FIRST_COMPLETED)
            if (inference in done and not interrupted.is_set() and not self.closed
                    and asyncio.get_running_loop().time() < job.expires):
                job.reply(inference.result(), "ok")
            elif not self.closed and job.peer not in self.pending:
                job.reply(1, "fallback")
        except (Exception, asyncio.CancelledError):
            if not self.closed and job.peer not in self.pending:
                job.reply(1, "fallback")
        finally:
            # Do not await a ranker that ignores cancellation. Our own deadline
            # releases the queue; the actual HTTP client closes its socket.
            inference.cancel()
            abort.cancel()
            self.active = None
            self.pump()

    def close(self):
        self.closed = True
        self.pending.clear()
        if self.timer:
            self.timer.cancel()
        if self.interrupted:
            self.interrupted.set()
