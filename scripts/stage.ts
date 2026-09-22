import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const target = resolve(import.meta.dir, "../.cache/rime-stage");
await mkdir(`${target}/lua`, { recursive: true });
await Bun.write(
  `${target}/lua/riwen.lua`,
  Bun.file(resolve(import.meta.dir, "../rime/lua/riwen.lua")),
);
await Bun.write(
  `${target}/rime_frost_double_pinyin_flypy.custom.yaml`,
  `# Staged patch for the inspected 雾凇小鹤 schema. Merge with existing customizations.
patch:
  "engine/processors/@before 0": lua_processor@*riwen*processor
  # Insert before pin_cand_filter so explicit pins retain precedence.
  "engine/filters/@before 4": lua_filter@*riwen*filter
  "riwen/port": 18765
`,
);
console.log(
  `Staged files in ${target}; active Rime configuration was not changed.`,
);
