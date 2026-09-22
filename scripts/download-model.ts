import { createHash } from "node:crypto";
import { mkdir, rename } from "node:fs/promises";
import { resolve } from "node:path";

const modelDir = resolve(import.meta.dir, "../.cache/models");
const target = `${modelDir}/qwen3-1.7b-q4_k_m.gguf`;
const expected =
  "72c5c3cb38fa32d5256e2fe30d03e7a64c6c79e668ad84057e3bd66e250b24fb";
async function verify(path: string) {
  const hash = createHash("sha256");
  for await (const chunk of Bun.file(path).stream()) hash.update(chunk);
  if (hash.digest("hex") !== expected)
    throw new Error("Model SHA-256 mismatch");
}
await mkdir(modelDir, { recursive: true });
if (await Bun.file(target).exists()) {
  await verify(target);
} else {
  const part = `${target}.part`;
  if (!(await Bun.file(part).exists())) {
    const proc = Bun.spawn(
      [
        "curl",
        "--fail",
        "--location",
        "--retry",
        "2",
        "--output",
        part,
        "https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_K_M.gguf",
      ],
      { stdout: "inherit", stderr: "inherit" },
    );
    if ((await proc.exited) !== 0)
      throw new Error(`Download failed; remove ${part} before retrying`);
  }
  await verify(part);
  await rename(part, target);
}
console.log(`Verified model: ${target}`);
