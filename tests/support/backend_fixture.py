"""Test-only stdio adapter: existing native tests exercise the Python UDP service."""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from riwen.model import Model
from riwen.server import start_server


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


async def main():
    options = json.loads(sys.argv[1])
    pending = {}
    sequence = 0
    model = Model(options["endpoint"])

    async def rank(request):
        nonlocal sequence
        sequence += 1
        token = sequence
        custom = options["corrector" if request.pinyin is not None else "ranker"]
        future = asyncio.get_running_loop().create_future()
        if custom:
            pending[token] = future
        data = asdict(request)
        if data["pinyin"] is None:
            del data["pinyin"]
        emit({"event": "request", "token": token, "request": data, "custom": custom})
        try:
            return await future if custom else await model(request)
        finally:
            pending.pop(token, None)
            emit({"event": "finished", "token": token})

    server = await start_server(options.get("port", 0), rank, debounce=options["debounceMs"] / 1000)
    emit({"event": "ready", "port": server.port})
    reader = asyncio.StreamReader()
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    current = asyncio.current_task()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, current.cancel)
    try:
        while line := await reader.readline():
            value = json.loads(line)
            future = pending.get(value["token"])
            if future and not future.done():
                if "error" in value:
                    future.set_exception(ValueError("Fixture model failure"))
                else:
                    future.set_result(value["value"])
    except asyncio.CancelledError:
        pass
    finally:
        server.close()
        if server.scheduler.runner:
            await server.scheduler.runner
        transport.close()


asyncio.run(main())
