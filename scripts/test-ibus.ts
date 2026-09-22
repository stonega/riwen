import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { createCorrector, createRanker } from "../src/model";
import { startServer } from "../src/server";
import { prepareProfile } from "./rime-profile";

const project = resolve(import.meta.dir, "..");
const root = `${project}/.cache/rime-profiles`;
await mkdir(root, { recursive: true });
const profile = await mkdtemp(`${root}/ibus-`);
const preferFirst = process.argv.includes("--prefer-first");
const correction = process.argv.includes("--correction");
const correct = createCorrector(
  process.env.RIWEN_MODEL_URL ?? "http://127.0.0.1:18080/v1/chat/completions",
);
let requests = 0;
const realModel = process.argv.includes("--model")
  ? createRanker(
      process.env.RIWEN_MODEL_URL ??
        "http://127.0.0.1:18080/v1/chat/completions",
    )
  : undefined;
const server = await startServer({
  port: 0,
  debounceMs: realModel ? 80 : 0,
  ranker: async (request, signal) => {
    requests++;
    if (realModel) return realModel(request, signal);
    await Bun.sleep(100);
    return preferFirst ? 1 : request.candidates.indexOf("程式") + 1;
  },
  corrector: async (request, signal) => {
    requests++;
    if (realModel) return correct(request, signal);
    await Bun.sleep(100);
    return "这是怎么回事";
  },
});
try {
  await prepareProfile(profile, server.port);
  const child = Bun.spawn(
    [
      "dbus-run-session",
      "--",
      "python",
      "tests/ibus_integration.py",
      profile,
      ...(preferFirst ? ["--prefer-first"] : []),
      ...(correction ? ["--correction"] : []),
    ],
    {
      cwd: project,
      stdout: "inherit",
      stderr: "inherit",
    },
  );
  if ((await child.exited) !== 0)
    throw new Error("Isolated IBus integration test failed");
  if (requests !== 1)
    throw new Error(
      `Expected one request; got ${requests}. Context leaked or private field was queried.`,
    );
} finally {
  server.close();
  await rm(profile, { recursive: true, force: true });
}
