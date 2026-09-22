import { startServer } from "../src/server";
import { createProbe } from "./native-probe";

// Use an ephemeral bridge port, so this demo does not compete with bridge:start.
const server = await startServer({ port: 0 });
let probe: Awaited<ReturnType<typeof createProbe>> | undefined;
try {
  probe = await createProbe(server.port);
  await probe.command("property riwen_mode auto");
  await probe.command("type woxpleyige");
  const context = await probe.command("key 32 0");
  console.log(`Committed by Rime: ${context.commit}`);
  const before = await probe.command("type igui");
  console.log(`Before: ${before.candidates.join(", ")}`);
  const started = performance.now();
  let after = before;
  for (let tick = 1; tick <= 50 && after.candidates[0] !== "程式"; tick++) {
    await Bun.sleep(40);
    after = await probe.command(`property riwen_poll ${tick}`);
  }
  if (after.candidates[0] !== "程式")
    throw new Error(
      `Expected 程式; model unavailable, late, or chose another candidate: ${after.candidates.join(", ")}`,
    );
  console.log(
    `After automatic polling (${Math.round(performance.now() - started)} ms): ${after.candidates.join(", ")}`,
  );
  console.log(`Space commits: ${(await probe.command("key 32 0")).commit}`);
} finally {
  server.close();
  await probe?.close();
}
