"""Production Python protocol, HTTP, scheduler and UDP regression tests."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from riwen.protocol import Request, decode_request, encode_request
from riwen.model import Model, local_endpoint, payload_for, valid_correction
from riwen.scheduler import Scheduler
from riwen.server import start_server

SAMPLE = Request("1", "我在写", "igui", ["城市", "程式"])
CORRECTION = Request("2", "", "veuizfmhhvui", ["这是怎忙会是"], "zhe shi zen mang hui shi")


class ProfileCompatibilityTest(unittest.TestCase):
    def test_safe_yaml_preserves_switch_labels_and_versions(self):
        from riwen.profile import read_yaml
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheme.yaml"
            path.write_text("states: [off, on, no, yes]\nversion: 2026-09-22\nenabled: true\ndisabled: false\n")
            value = read_yaml(path)
            self.assertEqual(value["states"], ["off", "on", "no", "yes"])
            self.assertEqual(value["version"], "2026-09-22")
            self.assertIs(value["enabled"], True)
            self.assertIs(value["disabled"], False)
            json.dumps(value)
            path.write_text("!!python/object/apply:os.system ['false']")
            with self.assertRaises(Exception):
                read_yaml(path)

    def test_profile_boundary_rejects_data_root_and_symlink_escape(self):
        from riwen import paths
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, outside = root / "data", root / "outside"
            data.mkdir()
            outside.mkdir()
            (data / "escape").symlink_to(outside, target_is_directory=True)
            with patch.object(paths, "DATA", data):
                for value in (data, outside, data / "escape/profile"):
                    with self.assertRaises(ValueError):
                        paths.isolated_profile(value)
                self.assertEqual(paths.isolated_profile(data / "app-profile"), data / "app-profile")


class ProtocolTest(unittest.TestCase):
    def test_roundtrip(self):
        for sample in (SAMPLE, CORRECTION, replace(SAMPLE, context="我在写\n文字\t测试")):
            self.assertEqual(decode_request(encode_request(sample)), sample)
        for raw in ("a", "chengshi", "hk", "1u;3", "A/B", "ab cd"):
            request = replace(SAMPLE, input=raw)
            self.assertEqual(decode_request(encode_request(request)), request)
        for pinyin in ("", "ㄓㄜˋ ㄕˋ", "zhè shì"):
            request = replace(CORRECTION, pinyin=pinyin)
            self.assertEqual(decode_request(encode_request(request)), request)

    def test_rejects_malformed_fields(self):
        changes = [{"context": ""}, {"context": "字" * 257}, {"input": "\x00aux"}, {"id": "0"},
                   {"id": "1١"}, {"candidates": ["one"]}, {"candidates": ["字"] * 9},
                   {"candidates": ["", "two"]}, {"candidates": ["x" * 193, "two"]}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode_request(replace(SAMPLE, **change))
        for packet in (b"R1\t1\tff\t6162\te59f8ee5b882\te7a88be5bc8f", b"x" * 12001,
                       b"R1\t1\t e6\t6162\te59f8ee5b882\te7a88be5bc8f", b"R2\t1"):
            with self.assertRaises(ValueError):
                decode_request(packet)
        for change in ({"pinyin": "bad\nfield"}, {"candidates": ["短词"]},
                       {"candidates": ["这是怎忙会是", "这是怎么回事"]}):
            with self.assertRaises(ValueError):
                encode_request(replace(CORRECTION, **change))

    def test_correction_guards(self):
        self.assertTrue(valid_correction("这是怎忙会是", "这是怎么回事"))
        for text in ("这是怎忙会是", "你好这是怎么回事", "这是怎么回事？", "我想去公园玩", "<script>", None):
            self.assertFalse(valid_correction("这是怎忙会是", text))

    def test_local_urls_only(self):
        for url in ("https://example.com/chat", "http://localhost/chat", "http://user:pass@127.0.0.1/chat",
                    "http://127.0.0.1/chat?q=a", "http://127.0.0.1/chat#x", "http://127.0.0.1\n/chat"):
            with self.assertRaises(ValueError):
                local_endpoint(url)

    def test_prompts_keep_constraints(self):
        payload = payload_for(SAMPLE, "qwen3-1.7b")
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["max_tokens"], 16)
        self.assertEqual(payload["response_format"]["json_schema"]["schema"]["properties"]["best"]["enum"], [1, 2])
        prompt = payload_for(CORRECTION, "qwen3-1.7b")["messages"][-1]["content"]
        self.assertIn(CORRECTION.input, prompt)
        self.assertIn(CORRECTION.candidates[0], prompt)
        self.assertNotIn(CORRECTION.pinyin, prompt)


@asynccontextmanager
async def http_fixture(callback):
    tasks = set()
    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            length = next(int(line.split(b":", 1)[1]) for line in headers.split(b"\r\n") if line.lower().startswith(b"content-length:"))
            payload = json.loads(await reader.readexactly(length))
            await callback(payload, reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/chat"
    finally:
        server.close()
        await server.wait_closed()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def answer(writer, message, status=200):
    data = json.dumps({"choices": [{"message": message}]}).encode()
    writer.write(f"HTTP/1.1 {status} Test\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data)
    await writer.drain()


class ModelTest(unittest.IsolatedAsyncioTestCase):
    async def test_structured_choice_and_correction_ignore_proxy(self):
        async def handle(payload, _reader, writer):
            self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
            key = "text" if payload["max_tokens"] == 64 else "best"
            await answer(writer, {"content": json.dumps({key: "这是怎么回事" if key == "text" else 2})})
        async with http_fixture(handle) as url:
            with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1"}):
                self.assertEqual(await Model(url)(SAMPLE), 2)
                self.assertEqual(await Model(url)(CORRECTION), "这是怎么回事")

    async def test_invalid_answers_and_redirects_fail(self):
        messages = [{"content": json.dumps({"best": value})} for value in (0, 3, "2", True)]
        messages += [{"content": "not json"}, {"content": '{"best":2}', "reasoning_content": "Thinking"}, {}]
        for message in messages:
            async def handle(_payload, _reader, writer):
                await answer(writer, message)
            async with http_fixture(handle) as url:
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    await Model(url)(SAMPLE)
        async def redirect(_payload, _reader, writer):
            writer.write(b"HTTP/1.1 302 Found\r\nLocation: https://example.com\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        async with http_fixture(redirect) as url:
            with self.assertRaisesRegex(ValueError, "302"):
                await Model(url)(SAMPLE)

    async def test_oversized_response(self):
        async def handle(_payload, _reader, writer):
            await answer(writer, {"content": "x" * 66000})
        async with http_fixture(handle) as url:
            with self.assertRaisesRegex(ValueError, "too large"):
                await Model(url)(SAMPLE)

    async def test_cancel_incomplete_response_closes_socket_and_recovers(self):
        for headers in (b"Content-Length: 1000\r\nConnection: close", b"Transfer-Encoding: chunked"):
            calls = 0
            disconnected = asyncio.Event()
            started = asyncio.Event()
            async def handle(_payload, reader, writer):
                nonlocal calls
                calls += 1
                if calls == 1:
                    writer.write(b"HTTP/1.1 200 OK\r\n" + headers + b"\r\n\r\n")
                    await writer.drain()
                    started.set()
                    await reader.read()
                    disconnected.set()
                else:
                    await answer(writer, {"content": '{"best":2}'})
            async with http_fixture(handle) as url:
                task = asyncio.create_task(Model(url)(SAMPLE))
                await asyncio.wait_for(started.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.wait_for(disconnected.wait(), 1)
                self.assertEqual(await Model(url)(SAMPLE), 2)


class SchedulerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schedulers = []

    async def asyncTearDown(self):
        for scheduler in self.schedulers:
            scheduler.close()
            if scheduler.runner:
                await scheduler.runner

    def scheduler(self, rank, **options):
        scheduler = Scheduler(rank, **options)
        self.schedulers.append(scheduler)
        return scheduler

    async def test_debounce_collapses_requests(self):
        calls, replies = [], []
        async def rank(request):
            calls.append(request.id)
            return 2
        scheduler = self.scheduler(rank, debounce=.01)
        scheduler.submit("a", SAMPLE, lambda *x: replies.append("old"))
        result = asyncio.get_running_loop().create_future()
        scheduler.submit("a", replace(SAMPLE, id="2"), lambda *x: result.set_result(x))
        self.assertEqual(await asyncio.wait_for(result, 1), (2, "ok"))
        self.assertEqual(calls, ["2"])
        self.assertEqual(replies, [])

    async def test_active_cancellation_discards_late_result(self):
        entered, release = asyncio.Event(), asyncio.Event()
        replies = []
        async def rank(request):
            if request.id == "1":
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()  # deliberately broken ranker
            return 2
        scheduler = self.scheduler(rank, debounce=0)
        scheduler.submit("a", SAMPLE, lambda *x: replies.append("old"))
        await entered.wait()
        result = asyncio.get_running_loop().create_future()
        scheduler.submit("a", replace(SAMPLE, id="2"), lambda *x: result.set_result(x))
        try:
            self.assertEqual(await asyncio.wait_for(result, 1), (2, "ok"))
        finally:
            release.set()
        await asyncio.sleep(.01)
        self.assertEqual(replies, [])

    async def test_timeout_and_model_failure_fall_back(self):
        for fail in (False, True):
            async def rank(_request):
                if fail:
                    raise ValueError("unavailable")
                await asyncio.Event().wait()
            scheduler = self.scheduler(rank, debounce=0, timeout=.02)
            result = asyncio.get_running_loop().create_future()
            scheduler.submit("a", SAMPLE, lambda *x: result.set_result(x))
            self.assertEqual(await asyncio.wait_for(result, 1), (1, "fallback"))

    async def test_queue_deadline_serialization_and_bound(self):
        calls = []
        async def rank(request):
            calls.append(request.id)
            await asyncio.sleep(.05)
            return 2
        scheduler = self.scheduler(rank, debounce=0, timeout=.025)
        results = []
        for index in range(34):
            scheduler.submit(str(index), replace(SAMPLE, id=str(index + 1)), lambda *x: results.append(x))
        self.assertLessEqual(len(scheduler.pending), 32)
        await asyncio.sleep(.09)
        self.assertEqual(len(results), 34)
        self.assertEqual(set(results), {(1, "fallback")})
        self.assertEqual(calls, ["1"])

    async def test_correction_deadline_and_close(self):
        async def rank(_request):
            await asyncio.sleep(.03)
            return "这是怎么回事"
        scheduler = self.scheduler(rank, debounce=0, timeout=.01, correction_debounce=.001, correction_timeout=.2)
        result = asyncio.get_running_loop().create_future()
        scheduler.submit("a", CORRECTION, lambda *x: result.set_result(x))
        self.assertEqual(await asyncio.wait_for(result, 1), ("这是怎么回事", "ok"))
        replies = []
        scheduler.submit("b", CORRECTION, lambda *x: replies.append(x))
        scheduler.close()
        await asyncio.sleep(.05)
        self.assertEqual(replies, [])


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_udp_correlated_result_and_invalid_packet_drop(self):
        seen = []
        async def rank(request):
            seen.append(request)
            return "这是怎么回事" if request.pinyin is not None else 2
        server = await start_server(rank=rank, debounce=0, correction_debounce=0)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setblocking(False)
        client.connect(("127.0.0.1", server.port))
        loop = asyncio.get_running_loop()
        try:
            await loop.sock_sendall(client, b"malformed")
            for request, expected in ((SAMPLE, b"R1\t1\t2\tok"), (CORRECTION, f"R2\t2\t{'这是怎么回事'.encode().hex()}\tok".encode())):
                await loop.sock_sendall(client, encode_request(request))
                self.assertEqual(await asyncio.wait_for(loop.sock_recv(client, 12000), 1), expected)
            self.assertEqual(seen, [SAMPLE, CORRECTION])
        finally:
            server.close()
            client.close()


if __name__ == "__main__":
    unittest.main()
