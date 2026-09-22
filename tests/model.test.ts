import { expect, test } from "bun:test";
import {
  createCorrector,
  createRanker,
  localEndpoint,
  validCorrection,
} from "../src/model";

const sample = {
  id: "1",
  context: "我在写",
  input: "igui",
  candidates: ["城市", "程式"],
};
test("corrections stay within the typed phrase and reject unchanged or excessive rewrites", () => {
  expect(validCorrection("这是怎忙会是", "这是怎么回事")).toBe(true);
  for (const text of [
    "这是怎忙会是",
    "你好这是怎么回事",
    "这是怎么回事？",
    "我想去公园玩",
    "<script>",
    null,
  ])
    expect(validCorrection("这是怎忙会是", text)).toBe(false);
});

test("corrector uses the original phrase and double pinyin and validates the reply", async () => {
  let answer = "这是怎么回事";
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const payload = (await request.json()) as {
        messages: { content: string }[];
      };
      expect(payload.messages.at(-1)?.content).toContain("veuizfmhhvui");
      expect(payload.messages.at(-1)?.content).toContain("这是怎忙会是");
      return Response.json({
        choices: [{ message: { content: JSON.stringify({ text: answer }) } }],
      });
    },
  });
  try {
    const correct = createCorrector(`http://127.0.0.1:${server.port}/chat`);
    const request = {
      id: "1",
      context: "",
      input: "veuizfmhhvui",
      pinyin: "zhe shi zen mang hui shi",
      candidates: ["这是怎忙会是"],
    };
    expect(await correct(request, AbortSignal.timeout(1000))).toBe(
      "这是怎么回事",
    );
    answer = "我想去公园玩";
    expect(await correct(request, AbortSignal.timeout(1000))).toBe("");
  } finally {
    server.stop(true);
  }
});
test("uses local structured output with thinking disabled", async () => {
  let payload: Record<string, unknown> = {};
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      payload = (await request.json()) as Record<string, unknown>;
      return Response.json({
        choices: [{ message: { content: '{"best":2}' } }],
      });
    },
  });
  try {
    expect(
      await createRanker(`http://127.0.0.1:${server.port}/v1/chat/completions`)(
        sample,
        AbortSignal.timeout(1000),
      ),
    ).toBe(2);
    expect(payload.chat_template_kwargs).toEqual({ enable_thinking: false });
    expect(payload.stream).toBe(false);
    expect(payload.max_tokens).toBe(16);
    expect(payload.response_format).toMatchObject({ type: "json_schema" });
  } finally {
    server.stop(true);
  }
});
test("rejects invalid model choices and hidden reasoning", async () => {
  for (const message of [
    { content: '{"best":0}' },
    { content: '{"best":3}' },
    { content: '{"best":"2"}' },
    { content: "not json" },
    { content: '{"best":2}', reasoning_content: "Thinking..." },
    {},
  ]) {
    const server = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch() {
        return Response.json({ choices: [{ message }] });
      },
    });
    try {
      await expect(
        createRanker(`http://127.0.0.1:${server.port}/chat`)(
          sample,
          AbortSignal.timeout(1000),
        ),
      ).rejects.toThrow();
    } finally {
      server.stop(true);
    }
  }
});
test("cannot redirect typing to another endpoint", async () => {
  for (const url of [
    "https://example.com/chat",
    "http://localhost/chat",
    "http://user:pass@127.0.0.1/chat",
  ]) {
    expect(() => localEndpoint(url)).toThrow();
  }
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch() {
      return Response.redirect("https://example.com", 302);
    },
  });
  try {
    await expect(
      createRanker(`http://127.0.0.1:${server.port}/chat`)(
        sample,
        AbortSignal.timeout(1000),
      ),
    ).rejects.toThrow();
  } finally {
    server.stop(true);
  }
});

test("an incomplete HTTP response aborts and the next request still succeeds", async () => {
  let calls = 0;
  let pending: ReadableStreamDefaultController<Uint8Array> | undefined;
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch() {
      if (++calls === 1)
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              pending = controller;
              controller.enqueue(new TextEncoder().encode('{"choices":'));
            },
            cancel() {
              pending = undefined;
            },
          }),
        );
      return Response.json({
        choices: [{ message: { content: '{"best":2}' } }],
      });
    },
  });
  try {
    const rank = createRanker(`http://127.0.0.1:${server.port}/chat`);
    await expect(rank(sample, AbortSignal.timeout(50))).rejects.toThrow();
    expect(await rank(sample, AbortSignal.timeout(1000))).toBe(2);
  } finally {
    pending?.close();
    server.stop(true);
  }
}, 1500);
