import Gio from "gi://Gio";
import GLib from "gi://GLib";

// All preparation and inference stay outside GNOME Shell's main loop.
export class RiwenService {
  constructor(path, settings) {
    this.path = `${path}/app`;
    this.settings = settings;
    this.process = null;
    this.done = null;
  }

  launcher(flags) {
    const launcher = new Gio.SubprocessLauncher({ flags });
    launcher.set_cwd(this.path);
    launcher.setenv("PYTHONDONTWRITEBYTECODE", "1", true);
    launcher.setenv(
      "RIWEN_SCHEMA",
      this.settings.get_string("schema-id"),
      true,
    );
    launcher.setenv(
      "RIWEN_CORRECTION",
      this.settings.get_boolean("correction") ? "1" : "0",
      true,
    );
    launcher.setenv(
      "RIWEN_CPU",
      this.settings.get_boolean("cpu") ? "1" : "0",
      true,
    );
    const source = this.settings.get_string("rime-source");
    launcher.setenv(
      "RIWEN_VOICE",
      this.settings.get_boolean("voice-enabled") ? "1" : "0",
      true,
    );
    if (source) launcher.setenv("RIWEN_RIME_SOURCE", source, true);
    return launcher;
  }

  async command(command) {
    const child = this.launcher(
      Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
    ).spawnv(["python3", `${this.path}/scripts/app.py`, command]);
    const timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 8, () => {
      child.force_exit();
      return GLib.SOURCE_CONTINUE;
    });
    try {
      return await new Promise((resolve, reject) => {
        child.communicate_utf8_async(null, null, (process, result) => {
          try {
            const [, stdout, stderr] = process.communicate_utf8_finish(result);
            if (!process.get_successful())
              throw new Error(stderr.trim() || "Riwen command failed");
            resolve(command === "stop" ? null : JSON.parse(stdout));
          } catch (error) {
            reject(error);
          }
        });
      });
    } finally {
      GLib.source_remove(timeout);
    }
  }

  start() {
    if (this.process) return;
    const child = this.launcher(
      Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
    ).spawnv(["python3", `${this.path}/scripts/app.py`, "start"]);
    this.process = child;
    this.done = new Promise((resolve) => {
      child.wait_async(null, (process, result) => {
        try {
          process.wait_finish(result);
        } finally {
          if (this.process === child) this.process = null;
          resolve();
        }
      });
    });
  }

  async stop() {
    if (this.process) {
      this.process.send_signal(15);
      await this.done;
    } else {
      await this.command("stop");
      const deadline = GLib.get_monotonic_time() + 30 * 1000000;
      while ((await this.command("status")).running) {
        if (GLib.get_monotonic_time() > deadline)
          throw new Error("Riwen is still stopping. Try again shortly.");
        await new Promise((resolve) =>
          GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
            resolve();
            return GLib.SOURCE_REMOVE;
          }),
        );
      }
    }
  }

  // Disable cannot await. The launcher handles SIGTERM and restores IBus before
  // terminating only its own child process groups.
  detach() {
    this.process?.send_signal(15);
  }
}
