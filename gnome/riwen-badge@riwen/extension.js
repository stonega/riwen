import Clutter from "gi://Clutter";
import Gio from "gi://Gio";
import GLib from "gi://GLib";
import St from "gi://St";
import {
  Extension,
  InjectionManager,
} from "resource:///org/gnome/shell/extensions/extension.js";
import { getIBusManager } from "resource:///org/gnome/shell/misc/ibusManager.js";
import * as Main from "resource:///org/gnome/shell/ui/main.js";
import * as PanelMenu from "resource:///org/gnome/shell/ui/panelMenu.js";
import * as PopupMenu from "resource:///org/gnome/shell/ui/popupMenu.js";
import { CandidateBadges } from "./badges.js";
import { RiwenService } from "./service.js";

export default class RiwenBadgeExtension extends Extension {
  enable() {
    try {
      this._enable();
    } catch (error) {
      this.disable();
      throw error;
    }
  }

  _enable() {
    this._active = true;
    this._changing = false;
    this._refreshing = false;
    this._loadingSchemes = false;
    this._settings = this.getSettings();
    this._service = new RiwenService(this.path, this._settings);
    // Center the popup below its button; Shell handles monitor-edge clamping.
    this._panel = new PanelMenu.Button(0.5, "Riwen");
    this._panel.add_child(
      new St.Icon({
        gicon: new Gio.FileIcon({
          file: this.dir.get_child("icons").get_child("riwen-symbolic.svg"),
        }),
        style_class: "system-status-icon",
        y_align: Clutter.ActorAlign.CENTER,
      }),
    );
    this._status = new PopupMenu.PopupMenuItem("Starting…", {
      reactive: false,
    });
    this._panel.menu.addMenuItem(this._status);
    this._toggle = new PopupMenu.PopupSwitchMenuItem("Qwen assistance", false);
    this._panel.menu.addMenuItem(this._toggle);
    this._toggle.connect("toggled", (_item, enabled) => {
      if (this._updating) return;
      if (this._settings.get_boolean("assistant-enabled") === enabled)
        this._change(false);
      else this._settings.set_boolean("assistant-enabled", enabled);
    });
    this._schemes = new PopupMenu.PopupSubMenuMenuItem("Rime scheme");
    this._panel.menu.addMenuItem(this._schemes);
    this._restart = this._panel.menu.addAction(
      "Restart to apply settings",
      () => this._change(true),
    );
    this._panel.menu.addAction("Settings…", () => this.openPreferences());
    this._panel.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
    this._voiceStatus = new PopupMenu.PopupMenuItem("Voice · F10 to prepare", {
      reactive: false,
    });
    this._panel.menu.addMenuItem(this._voiceStatus);
    this._panel.menu.addAction("Prepare voice model", () =>
      this._voiceCommand("voice-prepare"),
    );
    this._panel.menu.addAction("Cancel dictation", () =>
      this._voiceCommand("voice-cancel"),
    );
    this._panel.menu.connect("open-state-changed", (_menu, open) => {
      if (open) this._loadSchemes();
    });
    Main.panel.addToStatusArea(this.uuid, this._panel);
    this._settingsChanged = this._settings.connect(
      "changed",
      (_settings, key) => {
        if (key === "assistant-enabled") this._change(false);
        if (key === "show-badges") this._refreshBadges();
      },
    );
    this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
      this._refresh();
      return GLib.SOURCE_CONTINUE;
    });
    this._change(false);
    this._loadSchemes();
    this._installBadges();
  }

  async _change(restart) {
    if (this._changing) return;
    this._changing = true;
    const service = this._service;
    this._toggle.setSensitive(false);
    this._restart.setSensitive(false);
    try {
      await this._shutdown;
      if (!this._active || this._service !== service) return;
      if (restart || !this._settings.get_boolean("assistant-enabled"))
        await service.stop();
      if (
        this._active &&
        this._service === service &&
        this._settings.get_boolean("assistant-enabled")
      )
        service.start();
    } catch (error) {
      if (this._active && this._service === service)
        this._status.label.text = error.message;
    } finally {
      if (this._active && this._service === service) {
        this._changing = false;
        this._toggle.setSensitive(true);
        this._restart.setSensitive(true);
        this._refresh();
      }
    }
  }

  async _refresh() {
    if (this._refreshing) return;
    this._refreshing = true;
    const service = this._service;
    try {
      const status = await service.command("status");
      if (!this._active || this._service !== service) return;
      this._status.label.text =
        status.phase === "ready" ? `Ready · ${status.schema}` : status.message;
      this._updating = true;
      this._toggle.setToggleState(
        status.running || Boolean(this._service.process),
      );
      this._updating = false;
      const voice = await service.command("voice-status");
      if (this._active && this._service === service)
        this._voiceStatus.label.text = status.running
          ? voice.message
          : "Start Riwen to use voice input";
    } catch (error) {
      if (this._active && this._service === service)
        this._status.label.text = error.message;
    } finally {
      if (this._service === service) this._refreshing = false;
    }
  }

  async _voiceCommand(command) {
    const service = this._service;
    try {
      const result = await service.command(command);
      if (!this._active || this._service !== service) return;
      if (!result.ok) this._voiceStatus.label.text = result.message;
      else this._refresh();
    } catch (error) {
      if (this._active && this._service === service)
        this._voiceStatus.label.text = error.message;
    }
  }

  async _loadSchemes() {
    if (this._loadingSchemes) return;
    this._loadingSchemes = true;
    const service = this._service;
    try {
      const result = await service.command("schemas");
      if (!this._active || this._service !== service) return;
      this._schemes.menu.removeAll();
      const selected = this._settings.get_string("schema-id");
      for (const entry of [
        { id: "", name: "Follow Rime default" },
        ...result.schemes,
      ]) {
        const item = this._schemes.menu.addAction(entry.name, () => {
          this._settings.set_string("schema-id", entry.id);
          this._loadSchemes();
        });
        item.setOrnament(
          entry.id === selected
            ? PopupMenu.Ornament.DOT
            : PopupMenu.Ornament.NONE,
        );
      }
    } catch (error) {
      if (this._active && this._service === service) {
        this._schemes.menu.removeAll();
        this._schemes.menu.addMenuItem(
          new PopupMenu.PopupMenuItem(error.message, { reactive: false }),
        );
      }
    } finally {
      if (this._service === service) this._loadingSchemes = false;
    }
  }

  _refreshBadges() {
    this._injections?.clear();
    this._injections = null;
    this._badges?.destroy();
    this._badges = null;
    if (this._settings.get_boolean("show-badges")) this._installBadges();
  }

  _installBadges() {
    if (!this._settings.get_boolean("show-badges")) return;
    const manager = getIBusManager();
    const area = manager._candidatePopup?._candidateArea;
    if (!area?._candidateBoxes || typeof area.setCandidates !== "function") {
      throw new Error("Riwen badge: unsupported GNOME candidate popup");
    }

    this._badges = new CandidateBadges(
      area._candidateBoxes,
      () =>
        new St.Label({
          text: "Qwen",
          style_class: "riwen-qwen-badge",
          y_align: Clutter.ActorAlign.CENTER,
          reactive: false,
          can_focus: false,
        }),
    );
    this._injections = new InjectionManager();
    const badges = this._badges;
    try {
      this._injections.overrideMethod(
        area,
        "setCandidates",
        (original) =>
          function (indexes, candidates, cursorPosition, cursorVisible) {
            original.call(
              this,
              indexes,
              candidates,
              cursorPosition,
              cursorVisible,
            );
            badges.update(candidates, manager._currentEngineName === "riwen");
          },
      );
      badges.update(
        area._candidateBoxes.map((box) =>
          box.visible ? box._candidateLabel.text : "",
        ),
        manager._currentEngineName === "riwen",
      );
    } catch (error) {
      this.disable();
      throw error;
    }
  }

  disable() {
    this._active = false;
    if (this._timer) GLib.source_remove(this._timer);
    this._timer = 0;
    if (this._settingsChanged) this._settings.disconnect(this._settingsChanged);
    this._settingsChanged = 0;
    this._service?.detach();
    this._shutdown = this._service?.done;
    this._panel?.destroy();
    this._panel = null;
    this._injections?.clear();
    this._injections = null;
    this._badges?.destroy();
    this._badges = null;
  }
}
