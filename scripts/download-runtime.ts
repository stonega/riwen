import { createHash } from "node:crypto";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

if (process.platform !== "linux" || process.arch !== "x64") {
  throw new Error("This pinned Vulkan runtime is for Linux x86_64 only");
}
const cache = resolve(import.meta.dir, "../.cache");
const archive = `${cache}/llama-vulkan.tar.gz`;
const target = `${cache}/llama-vulkan`;
await mkdir(target, { recursive: true });
if (!(await Bun.file(archive).exists())) {
  const child = Bun.spawn(
    [
      "curl",
      "--fail",
      "--location",
      "--retry",
      "2",
      "--output",
      archive,
      "https://github.com/ggml-org/llama.cpp/releases/download/b10964/llama-b10964-bin-ubuntu-vulkan-x64.tar.gz",
    ],
    { stdout: "inherit", stderr: "inherit" },
  );
  if ((await child.exited) !== 0)
    throw new Error(`Download failed; remove ${archive} before retrying`);
}
const hash = createHash("sha256");
for await (const chunk of Bun.file(archive).stream()) hash.update(chunk);
if (
  hash.digest("hex") !==
  "55d1e58e14c11eedea090bf088fdeefbfe7b4b09ee03bf6dba9834651769afcf"
) {
  throw new Error("Runtime SHA-256 mismatch");
}
const extract = Bun.spawn(["tar", "-xzf", archive, "-C", target], {
  stdout: "inherit",
  stderr: "inherit",
});
if ((await extract.exited) !== 0) throw new Error("Runtime extraction failed");
console.log(`Verified local runtime: ${target}/llama-b10964/llama-server`);
