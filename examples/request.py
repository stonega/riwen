"""Send one example to a running local Riwen bridge."""
from pathlib import Path
import socket
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from riwen.protocol import Request, encode_request

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    client.settimeout(2.5)
    client.connect(("127.0.0.1", 18765))
    client.send(encode_request(Request("1", "我用Python写了一个", "igui", ["城市", "程式", "诚实"])))
    print(client.recv(12000).decode())
