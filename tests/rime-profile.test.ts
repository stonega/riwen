import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { discoverSchemes, prepareProfile } from "./support/profile";

test("profiles discover defaults and patch schemes without pin filters or custom Lua", async () => {
  const directory = await mkdtemp(`${tmpdir()}/riwen-profile-`);
  const source = `${directory}/source`;
  await mkdir(`${source}/build`, { recursive: true });
  try {
    await Bun.write(
      `${source}/build/default.yaml`,
      JSON.stringify({
        schema_list: [{ schema: "quanpin" }],
        menu: { page_size: 6 },
      }),
    );
    for (const [id, translator] of [
      ["quanpin", "script_translator"],
      ["shape", "table_translator"],
    ]) {
      await Bun.write(
        `${source}/build/${id}.schema.yaml`,
        JSON.stringify({
          schema: { schema_id: id, name: id },
          engine: {
            processors: ["speller"],
            translators: [translator],
            filters: ["simplifier", "uniquifier"],
          },
          speller: { alphabet: "abcXYZ123;", delimiter: " '" },
        }),
      );
    }
    await Bun.write(`${source}/secret.userdb.txt`, "must not be copied");
    expect((await discoverSchemes(source)).selected).toBe("quanpin");
    await Bun.write(
      `${source}/user.yaml`,
      "var:\n  previously_selected_schema: shape\n",
    );
    expect((await discoverSchemes(source)).selected).toBe("shape");
    for (const id of ["quanpin", "shape"]) {
      const target = `${directory}/${id}`;
      await prepareProfile(target, 18765, source, id);
      const schema = await Bun.file(`${target}/build/${id}.schema.yaml`).json();
      expect(schema.engine.filters).toEqual([
        "lua_filter@*riwen*filter",
        "simplifier",
        "uniquifier",
      ]);
      expect(schema.riwen.correction).toBe(id === "quanpin");
      expect(schema.riwen.alphabet).toContain("XYZ123;");
      expect(
        (await Bun.file(`${target}/riwen-profile.json`).json()).pageSize,
      ).toBe(6);
      expect(await Bun.file(`${target}/secret.userdb.txt`).exists()).toBe(
        false,
      );
      expect(await Bun.file(`${target}/lua/riwen.lua`).exists()).toBe(true);
    }
    expect(
      (
        Bun.YAML.parse(
          await Bun.file(`${source}/build/quanpin.schema.yaml`).text(),
        ) as { engine: { filters: string[] } }
      ).engine.filters,
    ).toEqual(["simplifier", "uniquifier"]);
    await expect(prepareProfile(source, 18765, source)).rejects.toThrow(
      "overwrite",
    );
    await expect(
      prepareProfile(`${directory}/bad`, 18765, source, "../unknown"),
    ).rejects.toThrow("not deployed");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
