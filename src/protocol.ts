export type RankRequest = {
  id: string;
  context: string;
  input: string;
  candidates: string[];
  // Present only for long-phrase correction requests (R2).
  pinyin?: string;
};

export const MAX_PACKET = 12_000;
const decoder = new TextDecoder("utf-8", { fatal: true });

function decodeHex(value: string, maxBytes: number): string {
  if (value.length > maxBytes * 2 || !/^(?:[\da-f]{2})*$/i.test(value)) {
    throw new Error("Invalid encoded field");
  }
  const result = decoder.decode(Buffer.from(value, "hex"));
  if (
    [...result].some(
      (char) => char.charCodeAt(0) < 32 && !"\t\n\r".includes(char),
    )
  ) {
    throw new Error("Control character in field");
  }
  return result;
}

export function decodeRequest(packet: Uint8Array): RankRequest {
  if (packet.byteLength > MAX_PACKET) throw new Error("Packet too large");
  const [version, id, context, input, ...fields] = decoder
    .decode(packet)
    .split("\t");
  const correction = version === "R2";
  const pinyin = correction ? fields.shift() : undefined;
  const candidates = fields;
  if (
    (version !== "R1" && !correction) ||
    !id ||
    !/^[1-9]\d{0,14}$/.test(id) ||
    context === undefined ||
    input === undefined ||
    candidates.length < (correction ? 1 : 2) ||
    (correction && candidates.length !== 1) ||
    candidates.length > 8
  )
    throw new Error("Invalid request");
  const request = {
    id,
    context: decodeHex(context, 768),
    input: decodeHex(input, 64),
    candidates: candidates.map((value) => decodeHex(value, 192)),
    ...(correction ? { pinyin: decodeHex(pinyin ?? "", 256) } : {}),
  };
  if (
    (!correction && !request.context.trim()) ||
    !/^[a-z']{2,64}$/.test(request.input) ||
    request.candidates.some((value) => !value.trim())
  ) {
    throw new Error("Empty context/candidate or unsupported input");
  }
  if (
    correction &&
    (!/^[a-z]+(?:[ '][a-z]+)*$/.test(request.pinyin ?? "") ||
      !/^[\u3400-\u9fff]{6,24}$/.test(request.candidates[0] ?? ""))
  )
    throw new Error("Unsupported correction request");
  return request;
}

export function encodeRequest(request: RankRequest): string {
  const hex = (value: string) => Buffer.from(value).toString("hex");
  const packet = [
    request.pinyin === undefined ? "R1" : "R2",
    request.id,
    hex(request.context),
    hex(request.input),
    ...(request.pinyin === undefined ? [] : [hex(request.pinyin)]),
    ...request.candidates.map(hex),
  ].join("\t");
  decodeRequest(Buffer.from(packet));
  return packet;
}

export function encodeCorrectionResponse(
  id: string,
  text: string,
  status: "ok" | "fallback",
) {
  return `R2\t${id}\t${Buffer.from(text).toString("hex")}\t${status}`;
}

export function encodeResponse(
  id: string,
  best: number,
  status: "ok" | "fallback",
) {
  return `R1\t${id}\t${best}\t${status}`;
}
