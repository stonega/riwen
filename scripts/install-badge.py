#!/usr/bin/env python3
"""Install the complete Riwen extension, without restarting the desktop."""

import importlib.util
import json
import os
import socket
import re
import shutil
import subprocess
from pathlib import Path

from gi.repository import Gio, GLib


def main():
    project = Path(__file__).resolve().parents[1]
    source = project / "gnome" / "riwen-badge@riwen"
    metadata = json.loads((source / "metadata.json").read_text())
    version = subprocess.check_output(["gnome-shell", "--version"], text=True)
    major = re.search(r"GNOME Shell (\d+)", version)
    if not major or major[1] not in metadata["shell-version"]:
        raise SystemExit("Riwen currently supports GNOME Shell 51 on Fedora x86_64.")

    settings = Gio.Settings.new("org.gnome.shell")
    if not settings.get_boolean("allow-extension-installation"):
        raise SystemExit("GNOME extension installation is disabled by desktop policy.")
    for key in ("enabled-extensions", "disabled-extensions"):
        if not settings.is_writable(key):
            raise SystemExit(f"GNOME setting {key} is locked by desktop policy.")

    uuid = metadata["uuid"]
    destination = Path(GLib.get_user_data_dir()) / "gnome-shell" / "extensions" / uuid
    # Refuse an in-place backend update while its launcher is active.
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(1)
        try:
            client.connect(str(destination / "app/.cache/app.sock"))
        except (FileNotFoundError, ConnectionRefusedError):
            pass
        else:
            raise SystemExit("Turn off Riwen in its panel menu before updating the extension.")
    spec = importlib.util.spec_from_file_location("package_extension", project / "scripts/package-extension.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    staged = package.build(project / ".cache/extension-install" / uuid)
    # Reuse already downloaded immutable assets without depending on this checkout.
    cache = destination / "app/.cache"
    for name in ("models", "llama-vulkan", "rime-native/rpms", "voice-models"):
        downloaded = project / ".cache" / name
        if downloaded.exists() and not (cache / name).exists():
            def link_or_copy(src, dst):
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
                return dst
            shutil.copytree(downloaded, cache / name, copy_function=link_or_copy)
    shutil.copytree(staged, destination, dirs_exist_ok=True)

    # A new UUID is discovered only at Shell startup. Queue it for the next
    # login, preserving every other extension and the global extensions switch.
    enabled = settings.get_strv("enabled-extensions")
    if uuid not in enabled:
        if not settings.set_strv("enabled-extensions", [*enabled, uuid]):
            raise SystemExit("Installed, but GNOME could not enable the badge.")
    disabled = settings.get_strv("disabled-extensions")
    if uuid in disabled:
        if not settings.set_strv("disabled-extensions", [x for x in disabled if x != uuid]):
            raise SystemExit("Installed, but GNOME could not remove the disabled flag.")
    Gio.Settings.sync()

    print(f"Installed the complete Riwen extension in {destination}")
    print("Sign out and sign back in once. Riwen will start automatically; use its panel menu for control.")
    if settings.get_boolean("disable-user-extensions"):
        print("User extensions are globally disabled; turn them on in GNOME Extensions.")


if __name__ == "__main__":
    main()
