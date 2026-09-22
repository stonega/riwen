import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { homedir } from "node:os";
import { resolve } from "node:path";

// Exercise the real launcher/bridge/frontend on a private bus, with a local model
// fixture. Its lifetime is external to the launcher and must survive shutdown.
const project = resolve(import.meta.dir, "..");
await mkdir(`${project}/.cache/rime-profiles`, { recursive: true });
const profile = await mkdtemp(`${project}/.cache/rime-profiles/launcher-`);
let requests = 0;
const model = Bun.serve({
  hostname: "127.0.0.1",
  port: 0,
  async fetch(request) {
    const path = new URL(request.url).pathname;
    if (path === "/health") return Response.json({ status: "ok" });
    if (path === "/v1/models")
      return Response.json({ data: [{ id: "qwen3-1.7b" }] });
    if (path !== "/v1/chat/completions")
      return new Response(null, { status: 404 });
    requests++;
    const body = (await request.json()) as { messages: { content: string }[] };
    const line = body.messages[1]?.content
      .split("\n")
      .find((line) => line.includes('"程式"'));
    await Bun.sleep(100);
    return Response.json({
      choices: [
        {
          message: {
            content: JSON.stringify({ best: Number.parseInt(line ?? "1", 10) }),
          },
        },
      ],
    });
  },
});
try {
  const child = Bun.spawn(
    [
      "dbus-run-session",
      "--",
      "python",
      "tests/ibus_integration.py",
      profile,
      "--launcher",
    ],
    {
      cwd: project,
      env: {
        ...process.env,
        RIWEN_MODEL_URL: `http://127.0.0.1:${model.port}/v1/chat/completions`,
        RIWEN_PROFILE: profile,
        RIWEN_RIME_SOURCE: resolve(
          process.env.XDG_CONFIG_HOME ?? `${homedir()}/.config`,
          "ibus/rime",
        ),
      },
      stdout: "inherit",
      stderr: "inherit",
    },
  );
  if ((await child.exited) !== 0)
    throw new Error("Launcher integration failed");
  if (requests !== 1)
    throw new Error(`Expected one inference; got ${requests}`);
  console.log("PASS: launcher reused the external model without stopping it");
} finally {
  model.stop(true);
  await rm(profile, { recursive: true, force: true });
}
