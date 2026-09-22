import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { prepareProfile } from "../tests/support/profile";

export type Snapshot = {
  input: string;
  commit: string;
  riwen_session: string;
  status: string;
  qwen_choice: string;
  selected: number;
  candidates: string[];
};

async function* lines(stream: ReadableStream<Uint8Array>) {
  const decoder = new TextDecoder();
  let pending = "";
  for await (const chunk of stream) {
    pending += decoder.decode(chunk, { stream: true });
    let end = pending.indexOf("\n");
    while (end >= 0) {
      yield pending.slice(0, end);
      pending = pending.slice(end + 1);
      end = pending.indexOf("\n");
    }
  }
}

export async function createProbe(
  port: number,
  schemaId = "rime_frost_double_pinyin_flypy",
  source?: string,
) {
  const project = resolve(import.meta.dir, "..");
  const native = `${project}/.cache/rime-native`;
  if (!(await Bun.file(`${native}/rime-probe`).exists())) {
    throw new Error("Run bun run rime:prepare first");
  }
  const profiles = `${project}/.cache/rime-profiles`;
  await mkdir(profiles, { recursive: true });
  const profile = await mkdtemp(`${profiles}/session-`);
  try {
    await prepareProfile(profile, port, source, schemaId);
  } catch (error) {
    await rm(profile, { recursive: true, force: true });
    throw error;
  }
  const child = Bun.spawn(
    [
      `${native}/rime-probe`,
      profile,
      `${native}/root/usr/lib64/rime-plugins/librime-lua.so`,
      schemaId,
    ],
    { stdin: "pipe", stdout: "pipe", stderr: "pipe" },
  );
  const stderr = new Response(child.stderr).text();
  const output = lines(child.stdout);
  async function next(): Promise<unknown> {
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const item = await Promise.race([
        output.next(),
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(
            () => reject(new Error("Rime probe response timed out")),
            5000,
          );
        }),
      ]);
      if (item.done) throw new Error(`Rime exited: ${await stderr}`);
      return JSON.parse(item.value);
    } finally {
      clearTimeout(timeout);
    }
  }
  async function close() {
    if (child.exitCode === null) {
      child.stdin.write("quit\n");
      child.stdin.end();
    }
    const timeout = setTimeout(() => child.kill(), 3000);
    try {
      await child.exited;
    } finally {
      clearTimeout(timeout);
      await rm(profile, { recursive: true, force: true });
    }
    const errors = await stderr;
    if (child.exitCode !== 0 || errors.trim())
      throw new Error(`Native Rime error: ${errors}`);
  }
  try {
    const ready = (await next()) as { ready?: boolean; lua?: boolean };
    if (!ready.ready || !ready.lua)
      throw new Error("Rime/Lua did not initialize");
  } catch (error) {
    child.kill();
    await child.exited;
    await rm(profile, { recursive: true, force: true });
    throw error;
  }
  return {
    async command(command: string): Promise<Snapshot> {
      if (/[\r\n]/.test(command)) throw new Error("One command per line");
      child.stdin.write(`${command}\n`);
      return (await next()) as Snapshot;
    },
    close,
  };
}

export async function waitForFirst(
  probe: Awaited<ReturnType<typeof createProbe>>,
  expected: string,
) {
  const deadline = performance.now() + 1500;
  let state: Snapshot;
  do {
    state = await probe.command("key 65477 0"); // F8, applied on the Rime thread.
    if (state.candidates[0] === expected) return state;
    await Bun.sleep(10);
  } while (performance.now() < deadline);
  throw new Error(`Expected ${expected}, got ${state.candidates.join(", ")}`);
}
