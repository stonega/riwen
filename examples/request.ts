import { encodeRequest } from "../src/protocol";

const timer = setTimeout(() => {
  console.error("No reply; is bun run bridge:start running?");
  socket.close();
  process.exitCode = 1;
}, 2500);
const socket = await Bun.udpSocket({
  hostname: "127.0.0.1",
  connect: { hostname: "127.0.0.1", port: 18765 },
  socket: {
    data(socket, packet) {
      console.log(packet.toString());
      clearTimeout(timer);
      socket.close();
    },
  },
});
socket.send(
  encodeRequest({
    id: "1",
    context: "我用Python写了一个",
    input: "igui",
    candidates: ["城市", "程式", "诚实"],
  }),
);
