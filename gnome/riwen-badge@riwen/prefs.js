import Adw from "gi://Adw";
import Gio from "gi://Gio";
import { ExtensionPreferences } from "resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js";

export default class RiwenPreferences extends ExtensionPreferences {
  fillPreferencesWindow(window) {
    const settings = this.getSettings();
    const page = new Adw.PreferencesPage({
      title: "Riwen",
      icon_name: "input-keyboard-symbolic",
    });
    window.add(page);
    const general = new Adw.PreferencesGroup({
      title: "Local Qwen assistance",
      description:
        "Use the Riwen panel menu to select a Rime scheme. First start downloads about 1.3 GB. All typing stays on this computer.",
    });
    page.add(general);
    for (const [key, title, subtitle] of [
      [
        "assistant-enabled",
        "Enable Riwen",
        "Also start automatically when the extension loads",
      ],
      [
        "show-badges",
        "Colored Qwen badges",
        "Show which candidates Qwen assisted",
      ],
      [
        "correction",
        "Phrase correction",
        "Limited corrections for phonetic schemes; restart Riwen to apply",
      ],
      [
        "cpu",
        "Use CPU",
        "For machines without a Vulkan GPU; slower, restart Riwen to apply",
      ],
      [
        "voice-enabled",
        "Local voice input",
        "F10 starts/finishes dictation; Esc cancels. Prepare once from the panel (about 879 MB). Restart Riwen to apply.",
      ],
    ]) {
      const row = new Adw.SwitchRow({ title, subtitle });
      settings.bind(key, row, "active", Gio.SettingsBindFlags.DEFAULT);
      general.add(row);
    }
    const advanced = new Adw.PreferencesGroup({
      title: "Rime profile",
      description:
        "Leave empty to use the existing IBus Rime profile. Only deployed schemes are available. Changes apply after restarting Riwen from its panel menu.",
    });
    page.add(advanced);
    const source = new Adw.EntryRow({
      title: "Rime profile folder (absolute path)",
    });
    settings.bind("rime-source", source, "text", Gio.SettingsBindFlags.DEFAULT);
    advanced.add(source);
  }
}
