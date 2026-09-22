// Real GJS/Gio processes; no GNOME desktop or IBus state is touched.
import Gio from "gi://Gio";
import GLib from "gi://GLib";
import { RiwenService } from "../gnome/riwen-badge@riwen/service.js";

function assert(value, message) {
  if (!value) throw new Error(message);
}
const directory = GLib.dir_make_tmp("riwen-service-XXXXXX");
GLib.mkdir_with_parents(`${directory}/app/scripts`, 448);
GLib.file_set_contents(
  `${directory}/app/scripts/app.py`,
  `
import json, os, signal, sys, time
from pathlib import Path
root = Path(__file__).resolve().parents[1]
state = root / 'state.json'
if sys.argv[1] == 'start':
    def stop(*_):
        state.unlink(missing_ok=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    state.write_text(json.dumps({'running': True, 'schema': os.environ.get('RIWEN_SCHEMA'), 'correction': os.environ.get('RIWEN_CORRECTION'), 'cpu': os.environ.get('RIWEN_CPU'), 'voice': os.environ.get('RIWEN_VOICE')}))
    while True: time.sleep(.02)
elif sys.argv[1] == 'status':
    print(state.read_text() if state.exists() else '{"running": false}')
elif sys.argv[1] == 'schemas':
    print('{"schemes": [{"id": "quanpin", "name": "全拼"}]}')
`,
);
const settings = {
  get_string: (key) => (key === "schema-id" ? "quanpin" : ""),
  get_boolean: (key) => key === "correction" || key === "voice-enabled",
};
const service = new RiwenService(directory, settings);
const loop = new GLib.MainLoop(null, false);
let failure;
(async () => {
  try {
    assert(
      (await service.command("schemas")).schemes[0].id === "quanpin",
      "Scheme enumeration failed",
    );
    service.start();
    const process = service.process;
    service.start();
    assert(service.process === process, "Duplicate process launched");
    let status;
    for (let i = 0; i < 30; i++) {
      status = await service.command("status");
      if (status.running) break;
    }
    assert(
      status.running &&
        status.schema === "quanpin" &&
        status.correction === "1" &&
        status.cpu === "0" &&
        status.voice === "1",
      "Settings did not reach helper",
    );
    await service.stop();
    assert(
      !service.process && !(await service.command("status")).running,
      "Stop leaked helper",
    );
    service.start();
    // Wait for the launcher's signal handlers before exercising disable.
    for (
      let i = 0;
      i < 30 && !(await service.command("status")).running;
      i++
    ) {}
    service.detach();
    await service.done;
    assert(!(await service.command("status")).running, "Disable leaked helper");
    print(
      "PASS: extension process ownership, settings, status, restart, and disable cleanup",
    );
  } catch (error) {
    failure = error;
  } finally {
    await service.stop();
    const cleanup = Gio.Subprocess.new(
      ["rm", "-rf", directory],
      Gio.SubprocessFlags.NONE,
    );
    cleanup.wait(null);
    loop.quit();
  }
})();
loop.run();
if (failure) throw failure;
