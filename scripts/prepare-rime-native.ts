import { mkdir, readdir } from "node:fs/promises";
import { resolve } from "node:path";

const project = resolve(import.meta.dir, "..");
const native = `${project}/.cache/rime-native`;
const root = `${native}/root`;
await mkdir(`${native}/rpms`, { recursive: true });
await mkdir(root, { recursive: true });
async function run(
  argv: string[],
  options: { cwd?: string; stdin?: Uint8Array } = {},
) {
  const child = Bun.spawn(argv, {
    cwd: options.cwd ?? project,
    stdin: options.stdin
      ? new Blob([options.stdin as Uint8Array<ArrayBuffer>])
      : "ignore",
    stdout: "inherit",
    stderr: "inherit",
  });
  if ((await child.exited) !== 0) throw new Error(`Command failed: ${argv[0]}`);
}
// Match the plugin's exact librime RPM release to the already installed library.
const query = Bun.spawnSync([
  "rpm",
  "-q",
  "--qf",
  "%{VERSION}-%{RELEASE}.%{ARCH}",
  "librime",
]);
if (query.exitCode !== 0)
  throw new Error(
    "This helper currently supports Fedora with librime installed",
  );
const release = query.stdout.toString().trim();
const packages = ["librime-lua", "librime-devel"].map(
  (name) => `${name}-${release}`,
);
for (const name of packages) {
  if (!(await Bun.file(`${native}/rpms/${name}.rpm`).exists())) {
    await run([
      "dnf",
      "--repo=fedora",
      "download",
      "--destdir",
      `${native}/rpms`,
      name,
    ]);
  }
}
for (const name of await readdir(`${native}/rpms`)) {
  if (!packages.some((pkg) => name === `${pkg}.rpm`)) continue;
  const unpack = Bun.spawn(["rpm2cpio", `${native}/rpms/${name}`], {
    stdout: "pipe",
    stderr: "inherit",
  });
  const archive = new Uint8Array(
    await new Response(unpack.stdout).arrayBuffer(),
  );
  if ((await unpack.exited) !== 0) throw new Error("RPM decoding failed");
  await run(["cpio", "-idmu", "--quiet"], { cwd: root, stdin: archive });
}
const common = [
  "g++",
  "-std=c++17",
  "-Wall",
  "-Wextra",
  "-Werror",
  "-Wno-missing-field-initializers",
  "-O2",
];
await run([
  ...common,
  "-shared",
  "-fPIC",
  `-I${root}/usr/include`,
  `${project}/src/native/rime_bridge.cpp`,
  "-Wl,-l:librime.so.1",
  "-ldl",
  "-o",
  `${native}/libriwen-rime.so`,
]);
await run([
  ...common,
  `-I${root}/usr/include`,
  `${project}/src/native/rime_probe.cpp`,
  `-L${native}`,
  "-lriwen-rime",
  "-Wl,-rpath,$ORIGIN",
  "-o",
  `${native}/rime-probe`,
]);
console.log(
  `Prepared matching Lua plugin and native probe under ${native}. No packages installed.`,
);
