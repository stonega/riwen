import { createCorrector, createRanker, type Ranker } from "./model";
import {
  decodeRequest,
  encodeCorrectionResponse,
  encodeResponse,
} from "./protocol";
import { Scheduler } from "./scheduler";

export async function startServer(
  options: {
    port?: number;
    ranker?: Ranker;
    corrector?: Ranker<string>;
    debounceMs?: number;
    timeoutMs?: number;
  } = {},
) {
  const endpoint =
    process.env.RIWEN_MODEL_URL ?? "http://127.0.0.1:18080/v1/chat/completions";
  const model = process.env.RIWEN_MODEL ?? "qwen3-1.7b";
  const rank = options.ranker ?? createRanker(endpoint, model);
  const correct = options.corrector ?? createCorrector(endpoint, model);
  const scheduler = new Scheduler<number | string>(
    (request, signal) =>
      request.pinyin === undefined
        ? rank(request, signal)
        : correct(request, signal),
    {
      debounceMs: options.debounceMs ?? 80,
      timeoutMs: options.timeoutMs ?? 1200,
    },
  );
  const socket = await Bun.udpSocket({
    hostname: "127.0.0.1",
    port: options.port ?? 18765,
    socket: {
      data(socket, packet, port, address) {
        if (address !== "127.0.0.1") return;
        try {
          const request = decodeRequest(packet);
          scheduler.submit(`${address}:${port}`, request, (best, status) => {
            socket.send(
              request.pinyin === undefined
                ? encodeResponse(
                    request.id,
                    typeof best === "number" ? best : 1,
                    status,
                  )
                : encodeCorrectionResponse(
                    request.id,
                    typeof best === "string" ? best : "",
                    status,
                  ),
              port,
              address,
            );
          });
        } catch {
          // Malformed packets are dropped. Never print typing context.
        }
      },
      error() {
        /* UDP loss is harmless: Rime retains native candidates. */
      },
    },
  });
  return {
    port: socket.port,
    close() {
      scheduler.close();
      socket.close();
    },
  };
}

if (import.meta.main) {
  const port = Number(process.env.RIWEN_PORT ?? 18765);
  if (!Number.isInteger(port) || port < 1024 || port > 65535)
    throw new Error("Invalid RIWEN_PORT");
  const server = await startServer({ port });
  console.log(
    `Riwen listening on 127.0.0.1:${server.port} (UDP); typing is not logged.`,
  );
  for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => {
      server.close();
      process.exit(0);
    });
  }
}
