import { expect, test } from "bun:test";
import { decodeRequest, encodeRequest } from "../src/protocol";

const sample = {
  id: "123",
  context: "我在写\n文字\t测试",
  input: "igui",
  candidates: ["城市", "程式"],
};
test("wire format preserves UTF-8 and field delimiters", () => {
  expect(decodeRequest(Buffer.from(encodeRequest(sample)))).toEqual(sample);
});
test("rejects malformed UTF-8, extra candidates, unsupported input, and oversized context", () => {
  expect(() =>
    decodeRequest(Buffer.from("R1\t1\tff\t6162\te59f8ee5b882\te7a88be5bc8f")),
  ).toThrow();
  for (const change of [
    { context: "" },
    { context: "字".repeat(257) },
    { input: "`aux" },
    { id: "0" },
    { candidates: ["one"] },
    { candidates: Array(9).fill("字") },
    { candidates: ["", "two"] },
    { candidates: ["x".repeat(193), "two"] },
  ])
    expect(() => encodeRequest({ ...sample, ...change })).toThrow();
  expect(() => decodeRequest(new Uint8Array(12001))).toThrow();
});

test("long-phrase requests carry pinyin and one original candidate without requiring context", () => {
  const correction = {
    id: "1",
    context: "",
    input: "veuizfmhhvui",
    pinyin: "zhe shi zen mang hui shi",
    candidates: ["这是怎忙会是"],
  };
  expect(decodeRequest(Buffer.from(encodeRequest(correction)))).toEqual(
    correction,
  );
  for (const change of [
    { pinyin: "" },
    { pinyin: "bad\nfield" },
    { candidates: ["短词"] },
    { candidates: ["这是怎忙会是", "这是怎么回事"] },
  ])
    expect(() => encodeRequest({ ...correction, ...change })).toThrow();
});
