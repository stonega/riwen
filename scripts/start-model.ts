import { resolve } from "node:path";

const model = resolve(
  import.meta.dir,
  "../.cache/models/qwen3-1.7b-q4_k_m.gguf",
);
if (!(await Bun.file(model).exists()))
  throw new Error("Run bun run model:download first");
const bundled = resolve(
  import.meta.dir,
  "../.cache/llama-vulkan/llama-b10964/llama-server",
);
const executable =
  process.env.RIWEN_LLAMA_SERVER ??
  ((await Bun.file(bundled).exists()) ? bundled : "llama-server");
const cpu = process.argv.includes("--cpu");
const port = Number(process.env.RIWEN_MODEL_PORT ?? 18080);
if (!Number.isInteger(port) || port < 1024 || port > 65535)
  throw new Error("Invalid RIWEN_MODEL_PORT");
let device = process.env.RIWEN_DEVICE;
if (!cpu) {
  const check = Bun.spawnSync([executable, "--list-devices"]);
  const output = check.stdout.toString();
  // On this hybrid laptop prefer NVIDIA over the integrated Intel GPU.
  device ??= output.match(/^\s*(\S+):[^\n]*NVIDIA/im)?.[1];
  if (check.exitCode !== 0 || !/Available devices:\s*\S/.test(output)) {
    throw new Error(
      "No GPU backend found. Run bun run runtime:download, use a CUDA-enabled llama-server, or pass --cpu.",
    );
  }
}
console.log(
  `Starting Qwen3-1.7B on ${cpu ? "CPU" : (device ?? "available GPU")}; model API http://127.0.0.1:${port}`,
);
const child = Bun.spawn(
  [
    executable,
    "--model",
    model,
    "--alias",
    "qwen3-1.7b",
    "--host",
    "127.0.0.1",
    "--port",
    String(port),
    "--ctx-size",
    "2048",
    "--parallel",
    "1",
    "--threads",
    "6",
    "--threads-batch",
    "6",
    "--n-gpu-layers",
    cpu ? "0" : "99",
    ...(device && !cpu ? ["--device", device] : []),
    "--jinja",
    "--reasoning",
    "off",
    "--reasoning-budget",
    "0",
    "--log-disable",
  ],
  { stdin: "ignore", stdout: "inherit", stderr: "inherit" },
);
for (const signal of ["SIGINT", "SIGTERM"] as const)
  process.on(signal, () => child.kill(signal));
process.exit(await child.exited);
