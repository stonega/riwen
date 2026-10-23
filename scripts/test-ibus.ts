import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { prepareProfile } from "../tests/support/profile";
import type { RankRequest } from "../tests/support/python-backend";
import { startServer } from "../tests/support/python-backend";

const project = resolve(import.meta.dir, "..");
const app = process.env.RIWEN_TEST_APP ?? project;
// Keep Unix socket names under sockaddr_un's 108-byte limit in installed apps.
const root = process.env.RIWEN_DATA_DIR ?? `${app}/.cache`;
await mkdir(root, { recursive: true });
const profile = await mkdtemp(`${root}/v-`);
const preferFirst = process.argv.includes("--prefer-first");
const correction = process.argv.includes("--correction");
const trigger = process.argv.includes("--trigger");
const voice = process.argv.includes("--voice");
const requests: RankRequest[] = [];
const realModel = process.argv.includes("--model");
const server = await startServer({
  port: 0,
  debounceMs: realModel ? 80 : 0,
  onRequest: (request) => {
    requests.push(request);
  },
  ranker: realModel
    ? undefined
    : async (request) => {
        await Bun.sleep(100);
        return preferFirst
          ? 1
          : Math.max(
              1,
              request.candidates.indexOf(
                trigger && request.input === "iufa" ? "触发" : "程式",
              ) + 1,
            );
      },
  corrector: realModel
    ? undefined
    : async () => {
        await Bun.sleep(100);
        return "你好这是怎么回事";
      },
});
try {
  await prepareProfile(
    profile,
    server.port,
    undefined,
    "rime_frost_double_pinyin_flypy",
  );
  const child = Bun.spawn(
    [
      "dbus-run-session",
      "--",
      "python",
      "tests/ibus_integration.py",
      profile,
      ...(preferFirst ? ["--prefer-first"] : []),
      ...(correction ? ["--correction"] : []),
      ...(trigger ? ["--trigger"] : []),
      ...(voice ? ["--voice"] : []),
    ],
    {
      cwd: project,
      env: { ...process.env, RIWEN_VOICE: voice ? "1" : "0" },
      stdout: "inherit",
      stderr: "inherit",
    },
  );
  if ((await child.exited) !== 0)
    throw new Error("Isolated IBus integration test failed");
  if (
    !requests.some(
      (request) => request.input === "igui" && request.context === "",
    )
  )
    throw new Error(
      "The new field did not receive a context-free ranking request",
    );
  if (
    !correction &&
    !trigger &&
    !requests.some(
      (request) => request.input === "igui" && request.context === "我写了一个",
    )
  )
    throw new Error("The original field lost its committed context");
  if (
    trigger &&
    !requests.some(
      (request) =>
        request.input === "iufa" &&
        request.context === "选词很不准确，且不经常",
    )
  )
    throw new Error(
      "Editing the screenshot spelling lost its committed context",
    );
} finally {
  server.close();
  await rm(profile, { recursive: true, force: true });
}
