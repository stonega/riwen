"""Bounded R1/R2 datagrams shared with the nonblocking Rime Lua client."""
from dataclasses import dataclass
import re

MAX_PACKET = 12000


@dataclass(frozen=True)
class Request:
    id: str
    context: str
    input: str
    candidates: list[str]
    pinyin: str | None = None


def decode_hex(value, limit):
    if len(value) > limit * 2 or not re.fullmatch(r"(?:[0-9a-fA-F]{2})*", value):
        raise ValueError("Invalid encoded field")
    result = bytes.fromhex(value).decode("utf-8")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in result):
        raise ValueError("Control character in field")
    return result


def decode_request(packet):
    if len(packet) > MAX_PACKET:
        raise ValueError("Packet too large")
    fields = packet.decode("utf-8").split("\t")
    if len(fields) < 6:
        raise ValueError("Invalid request")
    version, identifier, context, raw, *candidates = fields
    correction = version == "R2"
    pinyin = candidates.pop(0) if correction else None
    if (version not in ("R1", "R2") or not re.fullmatch(r"[1-9][0-9]{0,14}", identifier)
            or not (1 if correction else 2) <= len(candidates) <= 8
            or correction and len(candidates) != 1):
        raise ValueError("Invalid request")
    request = Request(identifier, decode_hex(context, 768), decode_hex(raw, 64),
                      [decode_hex(item, 192) for item in candidates],
                      decode_hex(pinyin, 256) if correction else None)
    if (not correction and not request.context.strip()
            or not re.fullmatch(r"[\x20-\x7e]{1,64}", request.input)
            or any(not value.strip() for value in request.candidates)):
        raise ValueError("Empty context/candidate or unsupported input")
    if correction and (any(ord(c) < 32 for c in request.pinyin)
                       or not re.fullmatch(r"[\u3400-\u9fff]{6,24}", request.candidates[0])):
        raise ValueError("Unsupported correction request")
    return request


def encode_request(request):
    values = [request.context, request.input]
    if request.pinyin is not None:
        values.append(request.pinyin)
    values.extend(request.candidates)
    packet = "\t".join(["R2" if request.pinyin is not None else "R1", request.id,
                        *(value.encode().hex() for value in values)]).encode()
    decode_request(packet)
    return packet


def encode_response(request, result, status):
    if request.pinyin is not None:
        value = result.encode().hex() if isinstance(result, str) else ""
        return f"R2\t{request.id}\t{value}\t{status}".encode()
    return f"R1\t{request.id}\t{result if type(result) is int else 1}\t{status}".encode()
