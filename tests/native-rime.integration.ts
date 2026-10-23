import { expect, test } from "bun:test";
import { createProbe, waitForFirst } from "../scripts/native-probe";
import type { RankRequest } from "./support/python-backend";
import { startServer } from "./support/python-backend";

test.each([
  ["veuizfmhhvui", "这是怎忙会是", "zhe shi zen mang hui shi", "这是怎么回事"],
  [
    "nihcveuizfmohvui",
    "你好这是怎抹灰是",
    "ni hao zhe shi zen mo hui shi",
    "你好这是怎么回事",
  ],
])(
  "correction of %s preserves the original, preedit, and clean commit",
  async (input, original, pinyin, expected) => {
    let received: RankRequest | undefined;
    const server = await startServer({
      port: 0,
      corrector: async (request) => {
        received = request;
        return expected;
      },
    });
    const probe = await createProbe(server.port);
    try {
      await probe.command("property riwen_mode auto");
      const before = await probe.command(`type ${input}`);
      expect(before.candidates[0]).toBe(original);
      expect(before.status).toBe("pending-correction");
      let after = before;
      for (let tick = 1; tick <= 80 && !after.qwen_choice; tick++) {
        await Bun.sleep(10);
        after = await probe.command(`property riwen_poll ${tick}`);
      }
      expect(received?.pinyin).toBe(pinyin);
      expect(received?.context).toBe("");
      expect(after.candidates[0]).toBe(expected);
      expect(after.candidates).toContain(original);
      expect(after.qwen_choice).toBe(expected);
      expect((after as unknown as { preedit: string }).preedit).toBe(pinyin);
      expect((await probe.command("key 32 0")).commit).toBe(expected);
    } finally {
      server.close();
      await probe.close();
    }
  },
);

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

test("first phrase after focus can receive an idle ranking", async () => {
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
    await probe.command("property riwen_mode auto");
    const before = await probe.command("type igui");
    expect(before.candidates[0]).toBe("城市");
    const after = await waitForFirst(probe, "程式");
    expect(received?.context).toBe("");
    expect(after.qwen_choice).toBe("程式");
    expect((await probe.command("key 32 0")).commit).toBe("程式");
  } finally {
    server.close();
    await probe.close();
  }
});

test("screenshot phrase keeps its context through a spelling edit and slow idle ranking", async () => {
  let received: RankRequest | undefined;
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async (request) => {
      if (request.input !== "iufa") return 1;
      received = request;
      await Bun.sleep(2100);
      return request.candidates.indexOf("触发") + 1;
    },
  });
  const probe = await createProbe(server.port);
  try {
    await probe.command("property riwen_mode auto");
    let committed = "";
    for (const input of ["xrci", "hf", "bu", "vyqt"]) {
      await probe.command(`type ${input}`);
      committed += (await probe.command("key 32 0")).commit;
    }
    committed += (await probe.command("key 44 0")).commit;
    for (const input of ["qp", "bu", "jkih"]) {
      await probe.command(`type ${input}`);
      committed += (await probe.command("key 32 0")).commit;
    }
    expect(committed).toBe("选词很不准确，且不经常");
    await probe.command("type iufx");
    await probe.command("key 65288 0"); // Correct only the active spelling.
    const before = await probe.command("type a");
    expect(before.candidates.slice(0, 4)).toEqual([
      "出发",
      "触发",
      "处罚",
      "除法",
    ]);
    const deadline = performance.now() + 3500;
    let after = before;
    for (
      let tick = 1;
      !after.qwen_choice && performance.now() < deadline;
      tick++
    ) {
      await Bun.sleep(40);
      after = await probe.command(`property riwen_poll ${tick}`);
    }
    expect(received?.context).toBe(committed);
    expect(received?.candidates).toEqual(before.candidates.slice(0, 4));
    expect(after.qwen_choice).toBe("触发");
    expect(after.candidates.slice(4)).toEqual(before.candidates.slice(4));
    expect((await probe.command("key 32 0")).commit).toBe("触发");
  } finally {
    server.close();
    await probe.close();
  }
});

test("two-key script input receives an automatic first-phrase ranking", async () => {
  let received: RankRequest | undefined;
  const server = await startServer({
    port: 0,
    debounceMs: 0,
    ranker: async (request) => {
      received = request;
      return 1;
    },
  });
  const probe = await createProbe(server.port);
  try {
    await probe.command("property riwen_mode auto");
    let after = await probe.command("type hf");
    expect(after.status).toBe("pending");
    for (let tick = 1; tick <= 50 && !after.qwen_choice; tick++) {
      await Bun.sleep(10);
      after = await probe.command(`property riwen_poll ${tick}`);
    }
    expect(received?.input).toBe("hf");
    expect(received?.context).toBe("");
    expect(after.qwen_choice).toBe("很");
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
