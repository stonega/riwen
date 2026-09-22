"""Local UDP bridge. Malformed datagrams are dropped without logging input."""
import asyncio
import os
import signal

from .model import Model
from .protocol import decode_request, encode_response
from .scheduler import Scheduler


class Server(asyncio.DatagramProtocol):
    def __init__(self, rank=None, **options):
        model = rank or Model(os.environ.get("RIWEN_MODEL_URL", "http://127.0.0.1:18080/v1/chat/completions"),
                              os.environ.get("RIWEN_MODEL", "qwen3-1.7b"))
        self.scheduler = Scheduler(model, **options)
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    @property
    def port(self):
        return self.transport.get_extra_info("sockname")[1]

    def datagram_received(self, packet, peer):
        if peer[0] != "127.0.0.1":
            return
        try:
            request = decode_request(packet)
        except (ValueError, UnicodeError):
            return
        self.scheduler.submit(peer, request,
                              lambda value, status: self.transport.sendto(encode_response(request, value, status), peer))

    def error_received(self, error):
        pass

    def close(self):
        self.scheduler.close()
        self.transport.close()


async def start_server(port=0, rank=None, **options):
    _, server = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: Server(rank, **options), local_addr=("127.0.0.1", port))
    return server


async def main():
    port = int(os.environ.get("RIWEN_PORT", "18765"))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid RIWEN_PORT")
    server = await start_server(port)
    stopped = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    print(f"Riwen listening on 127.0.0.1:{server.port} (UDP); typing is not logged.", flush=True)
    try:
        await stopped.wait()
    finally:
        server.close()
        if server.scheduler.runner:
            await server.scheduler.runner


if __name__ == "__main__":
    asyncio.run(main())
