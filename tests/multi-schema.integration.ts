import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { createProbe } from "../scripts/native-probe";
import { startServer } from "./support/python-backend";

test("real full-pinyin and table schemes rank without 小鹤 or pin_cand_filter", async () => {
  const root = resolve(import.meta.dir, "../.cache/rime-profiles");
  await mkdir(root, { recursive: true });
  const source = await mkdtemp(`${root}/multi-`);
  try {
    await Bun.write(
      `${source}/default.yaml`,
      JSON.stringify({
        config_version: "1",
        schema_list: [{ schema: "quanpin" }, { schema: "shape" }],
        menu: { page_size: 3 },
      }),
    );
    for (const id of ["quanpin", "shape"]) {
      await Bun.write(
        `${source}/${id}.schema.yaml`,
        JSON.stringify({
          schema: { schema_id: id, name: id, version: "1" },
          engine: {
            processors: [
              "ascii_composer",
              "speller",
              "selector",
              "navigator",
              "express_editor",
            ],
            segmentors: ["abc_segmentor", "fallback_segmentor"],
            translators: [
              id === "quanpin" ? "script_translator" : "table_translator",
            ],
            filters: ["uniquifier"],
          },
          speller: { alphabet: "abcdefghijklmnopqrstuvwxyz", delimiter: " '" },
          translator: {
            dictionary: id,
            enable_user_dict: false,
            enable_sentence: true,
          },
          ascii_composer: { switch_key: { Shift_L: "commit_code" } },
          menu: {
            page_size: 3,
            alternative_select_keys: id === "shape" ? "789" : "123",
          },
        }),
      );
      const words =
        id === "quanpin"
          ? "我\two\t100\n城市\tcheng shi\t100\n程式\tcheng shi\t50\n诚实\tcheng shi\t20\n这是怎忙会是\tzhe shi zen mang hui shi\t100\n"
          : "我\tw\t100\n城市\taa\t100\n程式\taa\t50\n诚实\taa\t20\n";
      await Bun.write(
        `${source}/${id}.dict.yaml`,
        `---\nname: ${id}\nversion: '1'\nsort: by_weight\n...\n${words}`,
      );
    }
    const deploy = Bun.spawn(
      [resolve(root, "../rime-native/rime-probe"), "--deploy", source],
      { stdout: "pipe", stderr: "pipe" },
    );
    const errors = await new Response(deploy.stderr).text();
    expect(await deploy.exited, errors).toBe(0);
    for (const id of ["quanpin", "shape"]) {
      const server = await startServer({
        port: 0,
        debounceMs: 0,
        ranker: async (request) => request.candidates.indexOf("程式") + 1,
        corrector: async () => "这是怎么回事",
      });
      const probe = await createProbe(server.port, id, source);
      try {
        await probe.command("property riwen_mode auto");
        await probe.command(`type ${id === "quanpin" ? "wo" : "w"}`);
        expect((await probe.command("key 32 0")).commit).toBe("我");
        let state = await probe.command(
          `type ${id === "quanpin" ? "chengshi" : "aa"}`,
        );
        expect(state.candidates[0]).toBe("城市");
        for (let tick = 1; tick <= 60 && !state.qwen_choice; tick++) {
          await Bun.sleep(10);
          state = await probe.command(`property riwen_poll ${tick}`);
        }
        expect(state.qwen_choice).toBe("程式");
        expect(state.candidates).toContain("城市");
        expect((state as unknown as { page_size: number }).page_size).toBe(3);
        expect((state as unknown as { labels: string[] }).labels).toEqual(
          id === "shape" ? ["7", "8", "9"] : ["1", "2", "3"],
        );
        expect((await probe.command("key 32 0")).commit).toBe("程式");
        if (id === "quanpin") {
          state = await probe.command("type zheshizenmanghuishi");
          expect(state.candidates[0]).toBe("这是怎忙会是");
          for (let tick = 70; tick < 150 && !state.qwen_choice; tick++) {
            await Bun.sleep(10);
            state = await probe.command(`property riwen_poll ${tick}`);
          }
          expect(state.qwen_choice).toBe("这是怎么回事");
          expect(state.candidates).toContain("这是怎忙会是");
          expect((await probe.command("key 32 0")).commit).toBe("这是怎么回事");
        }
      } finally {
        server.close();
        await probe.close();
      }
    }
  } finally {
    await rm(source, { recursive: true, force: true });
  }
}, 15000);
