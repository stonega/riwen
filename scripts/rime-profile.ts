import { cp, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { resolve } from "node:path";

export const schemaId = "rime_frost_double_pinyin_flypy";

/** Copy compiled static assets, never learned user databases or symlinks to them. */
export async function prepareProfile(
  target: string,
  port: number,
  source = resolve(
    process.env.XDG_CONFIG_HOME ?? `${homedir()}/.config`,
    "ibus/rime",
  ),
) {
  const schemaPath = `${source}/build/${schemaId}.schema.yaml`;
  const schema = Bun.YAML.parse(await Bun.file(schemaPath).text()) as {
    engine: { filters: string[]; processors: string[] };
    riwen?: { port: number };
  };
  const pinIndex = schema.engine.filters.findIndex((value) =>
    value.includes("pin_cand_filter"),
  );
  if (pinIndex < 0)
    throw new Error(
      "Expected pin_cand_filter; refusing to guess filter ordering",
    );
  schema.engine.processors.unshift("lua_processor@*riwen*processor");
  schema.engine.filters.splice(pinIndex, 0, "lua_filter@*riwen*filter");
  schema.riwen = { port };
  await mkdir(`${target}/build`, { recursive: true });
  const files = new Bun.Glob("*.{bin,yaml}");
  for await (const file of files.scan(`${source}/build`)) {
    await cp(`${source}/build/${file}`, `${target}/build/${file}`, {
      dereference: true,
    });
  }
  await cp(`${source}/lua`, `${target}/lua`, {
    recursive: true,
    dereference: true,
  });
  // Older 雾凇 aux_code assigns to a generic-for variable, which Lua 5.5 makes const.
  // Adapt only this disposable copy; the user's script is never modified.
  const auxPath = `${target}/lua/aux_code.lua`;
  if (await Bun.file(auxPath).exists()) {
    const aux = await Bun.file(auxPath).text();
    await Bun.write(
      auxPath,
      aux
        .replace(
          "            line = line:match",
          "            local line = line:match",
        )
        .replaceAll(
          "for cand in input:iter() do",
          "for original_cand in input:iter() do\n            local cand = original_cand",
        ),
    );
  }
  // Emoji/OpenCC assets are static. Missing optional assets are tolerated by Rime.
  if (await Bun.file(`${source}/opencc/emoji.json`).exists()) {
    await cp(`${source}/opencc`, `${target}/opencc`, {
      recursive: true,
      dereference: true,
    });
  }
  await Bun.write(
    `${target}/lua/riwen.lua`,
    Bun.file(resolve(import.meta.dir, "../rime/lua/riwen.lua")),
  );
  // JSON is valid YAML; compiled settings are private to this disposable profile.
  await Bun.write(
    `${target}/build/${schemaId}.schema.yaml`,
    JSON.stringify(schema, null, 2),
  );
  return target;
}
