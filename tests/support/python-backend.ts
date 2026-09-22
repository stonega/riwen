// Test fixture only. All transport, scheduling and model logic run in Python.
import { resolve } from "node:path";

export type RankRequest = {
  id: string;
  context: string;
  input: string;
  candidates: string[];
  pinyin?: string;
};
type Ranker = (
  request: RankRequest,
  signal: AbortSignal,
) => Promise<number | string>;

export function encodeRequest(request: RankRequest) {
  return [
    request.pinyin === undefined ? "R1" : "R2",
    request.id,
    ...[
      request.context,
      request.input,
      ...(request.pinyin === undefined ? [] : [request.pinyin]),
      ...request.candidates,
    ].map((value) => Buffer.from(value).toString("hex")),
  ].join("\t");
}

export async function startServer(
  options: {
    port?: number;
    ranker?: Ranker;
    corrector?: Ranker;
    debounceMs?: number;
    onRequest?: (request: RankRequest) => void;
  } = {},
) {
  const child = Bun.spawn(
    [
      "python3",
      resolve(import.meta.dir, "backend_fixture.py"),
      JSON.stringify({
        port: options.port ?? 0,
        ranker: Boolean(options.ranker),
        corrector: Boolean(options.corrector),
        debounceMs: options.debounceMs ?? 80,
        endpoint:
          process.env.RIWEN_MODEL_URL ??
          "http://127.0.0.1:18080/v1/chat/completions",
      }),
    ],
    { stdin: "pipe", stdout: "pipe", stderr: "pipe" },
  );
  const ready = Promise.withResolvers<number>();
  const controllers = new Map<number, AbortController>();
  let closed = false;
  const errors = new Response(child.stderr).text();
  const timer = setTimeout(() => {
    child.kill();
    ready.reject(new Error("Python bridge startup timed out"));
  }, 5000);
  const reading = (async () => {
    let pending = "";
    const decoder = new TextDecoder();
    for await (const chunk of child.stdout) {
      pending += decoder.decode(chunk, { stream: true });
      let end = pending.indexOf("\n");
      while (end >= 0) {
        const event = JSON.parse(pending.slice(0, end));
        pending = pending.slice(end + 1);
        end = pending.indexOf("\n");
        if (event.event === "ready") ready.resolve(event.port);
        else if (event.event === "finished") {
          controllers.get(event.token)?.abort();
          controllers.delete(event.token);
        } else if (event.event === "request") {
          options.onRequest?.(event.request);
          if (!event.custom) continue;
          const controller = new AbortController();
          controllers.set(event.token, controller);
          const rank =
            event.request.pinyin === undefined
              ? options.ranker
              : options.corrector;
          if (!rank) throw new Error("Missing fixture ranker");
          void rank(event.request, controller.signal).then(
            (value) => {
              if (!closed && !controller.signal.aborted)
                child.stdin.write(
                  `${JSON.stringify({ token: event.token, value })}\n`,
                );
            },
            () => {
              if (!closed && !controller.signal.aborted)
                child.stdin.write(
                  `${JSON.stringify({ token: event.token, error: true })}\n`,
                );
            },
          );
        }
      }
    }
    const code = await child.exited;
    if (!closed)
      throw new Error(`Python bridge exited (${code}): ${await errors}`);
  })();
  reading.catch((error) => ready.reject(error));
  try {
    const port = await ready.promise;
    return {
      port,
      close() {
        closed = true;
        for (const controller of controllers.values()) controller.abort();
        child.stdin.end();
        child.kill();
      },
    };
  } catch (error) {
    closed = true;
    child.kill();
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
