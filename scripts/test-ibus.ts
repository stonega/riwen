import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { prepareProfile } from "../tests/support/profile";
import { startServer } from "../tests/support/python-backend";

const project = resolve(import.meta.dir, "..");
const app = process.env.RIWEN_TEST_APP ?? project;
// Keep Unix socket names under sockaddr_un's 108-byte limit in installed apps.
const root = process.env.RIWEN_DATA_DIR ?? `${app}/.cache`;
await mkdir(root, { recursive: true });
const profile = await mkdtemp(`${root}/v-`);
const preferFirst = process.argv.includes("--prefer-first");
const correction = process.argv.includes("--correction");
const voice = process.argv.includes("--voice");
let requests = 0;
const realModel = process.argv.includes("--model");
const server = await startServer({
  port: 0,
  debounceMs: realModel ? 80 : 0,
  onRequest: () => {
    requests++;
  },
  ranker: realModel
    ? undefined
    : async (request) => {
        await Bun.sleep(100);
        return preferFirst ? 1 : request.candidates.indexOf("程式") + 1;
      },
  corrector: realModel
    ? undefined
    : async () => {
        await Bun.sleep(100);
        return "这是怎么回事";
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
  if (requests !== 1)
    throw new Error(
      `Expected one request; got ${requests}. Context leaked or private field was queried.`,
    );
} finally {
  server.close();
  await rm(profile, { recursive: true, force: true });
}
