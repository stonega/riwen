import { expect, test } from "bun:test";
import { encodeRequest, startServer } from "./support/python-backend";

test("real Lua extension submits and visibly applies a service ranking", async () => {
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async () => 2,
  });
  try {
    const child = Bun.spawn(
      ["lua", "examples/rime-demo.lua", String(server.port)],
      { stdout: "pipe", stderr: "pipe" },
    );
    const output = await new Response(child.stdout).text();
    expect(await child.exited).toBe(0);
    expect(output).toContain("Before: 城市, 程式, 诚实");
    expect(output).toContain("After: 程式, 城市, 诚实");
  } finally {
    server.close();
  }
});

test("real UDP request reaches the ranker and returns a correlated result", async () => {
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async (request) => {
      expect(request.context).toBe("我在写");
      return 2;
    },
  });
  const response = Promise.withResolvers<string>();
  const client = await Bun.udpSocket({
    hostname: "127.0.0.1",
    connect: { hostname: "127.0.0.1", port: server.port },
    socket: {
      data(_socket, data) {
        response.resolve(data.toString());
      },
    },
  });
  try {
    client.send(
      encodeRequest({
        id: "51",
        context: "我在写",
        input: "igui",
        candidates: ["城市", "程式"],
      }),
    );
    expect(await response.promise).toBe("R1\t51\t2\tok");
  } finally {
    client.close();
    server.close();
  }
});

test("LuaSocket speaks the same protocol as the Python service", async () => {
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async () => 2,
  });
  try {
    const script = `local s=require('socket'); local u=assert(s.udp()); u:settimeout(2); assert(u:setpeername('127.0.0.1', ${server.port})); assert(u:send(${JSON.stringify(encodeRequest({ id: "7", context: "我在写", input: "igui", candidates: ["城市", "程式"] }))})); print(assert(u:receive())); u:close()`;
    const child = Bun.spawn(["lua", "-e", script], {
      stdout: "pipe",
      stderr: "pipe",
    });
    expect(await child.exited).toBe(0);
    expect((await new Response(child.stdout).text()).trim()).toBe(
      "R1\t7\t2\tok",
    );
  } finally {
    server.close();
  }
});
