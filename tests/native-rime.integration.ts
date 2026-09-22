import { expect, test } from "bun:test";
import { createProbe, waitForFirst } from "../scripts/native-probe";
import type { RankRequest } from "../src/protocol";
import { startServer } from "../src/server";

test("long-phrase correction preserves the original, preedit, and clean commit", async () => {
  let received: RankRequest | undefined;
  const server = await startServer({
    port: 0,
    corrector: async (request) => {
      received = request;
      return "这是怎么回事";
    },
  });
  const probe = await createProbe(server.port);
  try {
    await probe.command("property riwen_mode auto");
    const before = await probe.command("type veuizfmhhvui");
    expect(before.candidates[0]).toBe("这是怎忙会是");
    expect(before.status).toBe("pending-correction");
    let after = before;
    for (let tick = 1; tick <= 80 && !after.qwen_choice; tick++) {
      await Bun.sleep(10);
      after = await probe.command(`property riwen_poll ${tick}`);
    }
    expect(received?.pinyin).toBe("zhe shi zen mang hui shi");
    expect(after.candidates[0]).toBe("这是怎么回事");
    expect(after.candidates).toContain("这是怎忙会是");
    expect(after.qwen_choice).toBe("这是怎么回事");
    expect((await probe.command("key 32 0")).commit).toBe("这是怎么回事");
  } finally {
    server.close();
    await probe.close();
  }
});

test("late corrections do not replace a committed phrase or a navigated menu", async () => {
  for (const key of ["key 32 0", "key 65364 0", "property riwen_reset 1"]) {
    const started = Promise.withResolvers<void>();
    const release = Promise.withResolvers<string>();
    const server = await startServer({
      port: 0,
      corrector: async () => {
        started.resolve();
        return release.promise;
      },
    });
    const probe = await createProbe(server.port);
    try {
      await probe.command("property riwen_mode auto");
      await probe.command("type veuizfmhhvui");
      await started.promise;
      const before = await probe.command(key);
      if (key === "key 32 0") expect(before.commit).toBe("这是怎忙会是");
      release.resolve("这是怎么回事");
      await Bun.sleep(30);
      const after = await probe.command("property riwen_poll 1");
      expect(after.candidates).toEqual(before.candidates);
      expect(after.qwen_choice).toBe("");
    } finally {
      release.resolve("");
      server.close();
      await probe.close();
    }
  }
});

test("main-thread idle polling applies automatically without F8", async () => {
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async (request) => request.candidates.indexOf("程式") + 1,
  });
  const probe = await createProbe(server.port);
  try {
    await probe.command("property riwen_mode auto");
    await probe.command("type woxpleyige");
    await probe.command("key 32 0");
    expect((await probe.command("type igui")).candidates[0]).toBe("城市");
    let after = await probe.command("get");
    for (let tick = 1; tick <= 50 && after.candidates[0] !== "程式"; tick++) {
      await Bun.sleep(10);
      after = await probe.command(`property riwen_poll ${tick}`);
    }
    expect(after.candidates[0]).toBe("程式");
    expect(after.status).toBe("applied");
    expect(after.qwen_choice).toBe("程式");
    expect((await probe.command("property riwen_reset 1")).qwen_choice).toBe(
      "",
    );
  } finally {
    server.close();
    await probe.close();
  }
});

test("idle results cannot reorder after candidate navigation or focus reset", async () => {
  for (const action of ["key 65364 0", "property riwen_reset 1"]) {
    const reached = Promise.withResolvers<void>();
    const release = Promise.withResolvers<void>();
    const server = await startServer({
      port: 0,
      debounceMs: 0,
      ranker: async (request) => {
        reached.resolve();
        await release.promise;
        return request.candidates.indexOf("程式") + 1;
      },
    });
    const probe = await createProbe(server.port);
    try {
      await probe.command("property riwen_mode auto");
      await probe.command("type wo");
      await probe.command("key 32 0");
      await probe.command("type igui");
      await reached.promise;
      const before = await probe.command(action);
      release.resolve();
      for (let tick = 1; tick <= 5; tick++) {
        await Bun.sleep(10);
        const after = await probe.command(`property riwen_poll ${tick}`);
        expect(after.candidates).toEqual(before.candidates);
        expect(after.selected).toBe(before.selected);
      }
    } finally {
      release.resolve();
      server.close();
      await probe.close();
    }
  }
});

test("actual 小鹤 dictionary → LuaSocket → ranking service → real Rime candidates", async () => {
  let received: RankRequest | undefined;
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async (request) => {
      received = request;
      return request.candidates.indexOf("程式") + 1;
    },
  });
  const probe = await createProbe(server.port);
  try {
    await probe.command("type woxpleyige");
    expect((await probe.command("key 32 0")).commit).toBe("我写了一个");
    const before = await probe.command("type igui");
    expect(before.candidates[0]).toBe("城市");
    expect(before.candidates).toContain("程式");
    expect(before.qwen_choice).toBe("");
    expect(before.riwen_session).not.toBe("");
    const after = await waitForFirst(probe, "程式");
    expect(received?.context).toBe("我写了一个");
    expect(received?.input).toBe("igui");
    expect(after.candidates).toContain("城市");
    expect(after.qwen_choice).toBe("程式");
    const committed = await probe.command("key 32 0");
    expect(committed.commit).toBe("程式");
    expect(committed.qwen_choice).toBe("");
  } finally {
    server.close();
    await probe.close();
  }
});

test("a pending response never changes what Space commits", async () => {
  const reached = Promise.withResolvers<void>();
  const release = Promise.withResolvers<void>();
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async (request) => {
      reached.resolve();
      await release.promise;
      return request.candidates.indexOf("程式") + 1;
    },
  });
  const probe = await createProbe(server.port);
  try {
    await probe.command("type wo");
    await probe.command("key 32 0");
    const before = await probe.command("type igui");
    await reached.promise;
    release.resolve();
    expect((await probe.command("key 32 0")).commit).toEqual(
      before.candidates[0] ?? "",
    );
  } finally {
    release.resolve();
    server.close();
    await probe.close();
  }
});

test("no service leaves conversion and F8 usable", async () => {
  const socket = await Bun.udpSocket({ hostname: "127.0.0.1", port: 0 });
  const port = socket.port;
  socket.close();
  const probe = await createProbe(port);
  try {
    await probe.command("type wo");
    await probe.command("key 32 0");
    const before = await probe.command("type igui");
    const after = await probe.command("key 65477 0");
    expect(after.candidates).toEqual(before.candidates);
    expect(after.qwen_choice).toBe("");
    expect((await probe.command("key 32 0")).commit).toEqual(
      before.candidates[0] ?? "",
    );
  } finally {
    await probe.close();
  }
});
