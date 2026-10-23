"""Send one example to a running local Riwen bridge."""
from pathlib import Path
import os
import socket
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from riwen.protocol import Request, encode_request

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    client.settimeout(4.5)
    client.connect(("127.0.0.1", int(os.environ.get("RIWEN_PORT", "18765"))))
    context = "" if "--first" in sys.argv[1:] else "我用Python写了一个"
    request = Request("1", context, "igui", ["城市", "程式", "诚实"])
    if "--trigger" in sys.argv[1:]:
        request = Request("1", "选词很不准确，且不经常", "iufa", ["出发", "触发", "处罚", "除法"])
    client.send(encode_request(request))
    print(client.recv(12000).decode())
