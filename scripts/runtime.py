#!/usr/bin/env python3
"""Python entry point for development and installed Riwen runtime operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from riwen.paths import DATA, NATIVE, PACKAGED, PLUGIN, PROJECT, isolated_profile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def download(url, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    if not target.exists() and not part.exists():
        run("curl", "--fail", "--location", "--retry", "2", "--output", str(part), url)
    candidate = target if target.exists() else part
    with candidate.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch; remove {candidate} and retry")
    if candidate == part:
        part.replace(target)
    return target


def prepare_native():
    if PACKAGED:
        if not (NATIVE / "libriwen-rime.so").is_file() or not PLUGIN.is_file():
            raise RuntimeError("Missing packaged Rime support; reinstall Riwen and librime-lua")
        return
    NATIVE.mkdir(parents=True, exist_ok=True)
    rpms = NATIVE / "rpms"
    rpms.mkdir(exist_ok=True)
    release = subprocess.check_output(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}.%{ARCH}", "librime"], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="staging-", dir=NATIVE) as directory:
        root = Path(directory)
        for name in ("librime-lua", "librime-devel"):
            package = f"{name}-{release}"
            archive = rpms / f"{package}.rpm"
            if not archive.exists():
                run("dnf", "--repo=fedora", "download", "--destdir", str(rpms), package)
            payload = subprocess.check_output(["rpm2cpio", str(archive)])
            run("cpio", "-idmu", "--quiet", cwd=root, input=payload)
        common = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers", "-O2", f"-I{root}/usr/include"]
        run(*common, "-shared", "-fPIC", str(PROJECT / "src/native/rime_bridge.cpp"),
            "-Wl,-l:librime.so.1", "-ldl", "-o", str(NATIVE / "libriwen-rime.so.new"))
        (NATIVE / "libriwen-rime.so.new").replace(NATIVE / "libriwen-rime.so")
        run(*common, str(PROJECT / "src/native/rime_probe.cpp"), f"-L{NATIVE}", "-lriwen-rime",
            "-Wl,-l:librime.so.1", "-Wl,-rpath,$ORIGIN", "-o", str(NATIVE / "rime-probe.new"))
        (NATIVE / "rime-probe.new").replace(NATIVE / "rime-probe")
        PLUGIN.parent.mkdir(parents=True, exist_ok=True)
        (root / "usr/lib64/rime-plugins/librime-lua.so").replace(PLUGIN)
    print(f"Prepared matching native support under {NATIVE}. No packages installed.")


def start_model(cpu=False):
    import re
    model = DATA / "models/qwen3-1.7b-q4_k_m.gguf"
    if not model.is_file():
        raise RuntimeError("Run python3 scripts/runtime.py model-download first")
    bundled = DATA / "llama-vulkan/llama-b10964/llama-server"
    executable = os.environ.get("RIWEN_LLAMA_SERVER") or (str(bundled) if bundled.exists() else "llama-server")
    port = int(os.environ.get("RIWEN_MODEL_PORT", "18080"))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid RIWEN_MODEL_PORT")
    device = os.environ.get("RIWEN_DEVICE")
    if not cpu:
        check = subprocess.run([executable, "--list-devices"], capture_output=True, text=True)
        match = re.search(r"^\s*(\S+):[^\n]*NVIDIA", check.stdout, re.M | re.I)
        device = device or (match[1] if match else None)
        if check.returncode or not re.search(r"Available devices:\s*\S", check.stdout):
            raise RuntimeError("No GPU backend found. Download the Vulkan runtime or use --cpu.")
    child = subprocess.Popen([executable, "--model", str(model), "--alias", "qwen3-1.7b", "--host", "127.0.0.1",
                              "--port", str(port), "--ctx-size", "2048", "--parallel", "1", "--threads", "6",
                              "--threads-batch", "6", "--n-gpu-layers", "0" if cpu else "99",
                              *(["--device", device] if device and not cpu else []),
                              "--jinja", "--reasoning", "off", "--reasoning-budget", "0", "--log-disable"],
                             stdin=subprocess.DEVNULL)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda number, _: child.send_signal(number) if child.poll() is None else None)
    return child.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("bridge", "schemas", "profile", "ibus-prepare", "rime-prepare", "model-download", "runtime-download", "model-start", "stage"))
    parser.add_argument("--source")
    parser.add_argument("--target")
    parser.add_argument("--schema")
    parser.add_argument("--port", type=int, default=int(os.environ.get("RIWEN_PORT", "18765")))
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    if args.command == "bridge":
        import asyncio
        from riwen.server import main as serve
        asyncio.run(serve())
    elif args.command in ("schemas", "profile", "ibus-prepare", "stage"):
        from riwen.profile import discover_schemes, prepare_profile, selected_scheme, settings, source_path, write_json
        source = args.source or source_path()
        if args.command == "schemas":
            print(json.dumps(discover_schemes(source), ensure_ascii=False))
        elif args.command in ("profile", "ibus-prepare"):
            target = args.target or os.environ.get("RIWEN_PROFILE") or DATA / "ibus-profile"
            if args.command == "ibus-prepare":
                target = isolated_profile(target)
            print(json.dumps(prepare_profile(target, args.port, source, args.schema)))
        else:
            if not 1024 <= args.port <= 65535:
                raise ValueError("Invalid RIWEN_PORT")
            scheme, schema = selected_scheme(source, args.schema)
            target = DATA / "rime-stage"
            (target / "lua").mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / "rime/lua/riwen.lua", target / "lua/riwen.lua")
            patch = {"engine/processors/@before 0": "lua_processor@*riwen*processor",
                     "engine/filters": ["lua_filter@*riwen*filter", *(v for v in schema["engine"].get("filters", []) if "riwen" not in v)],
                     **{f"riwen/{key}": value for key, value in settings(scheme, schema, args.port).items()}}
            write_json(target / f"{scheme['id']}.custom.yaml", {"patch": patch})
            print(f"Staged {scheme['name']} in {target}; active Rime configuration was not changed.")
    elif args.command == "rime-prepare":
        prepare_native()
    elif args.command == "model-download":
        download("https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_K_M.gguf",
                 DATA / "models/qwen3-1.7b-q4_k_m.gguf", "72c5c3cb38fa32d5256e2fe30d03e7a64c6c79e668ad84057e3bd66e250b24fb")
    elif args.command == "runtime-download":
        import platform
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            raise RuntimeError("The pinned Vulkan runtime requires Linux x86_64")
        archive = download("https://github.com/ggml-org/llama.cpp/releases/download/b10964/llama-b10964-bin-ubuntu-vulkan-x64.tar.gz",
                           DATA / "llama-vulkan.tar.gz", "55d1e58e14c11eedea090bf088fdeefbfe7b4b09ee03bf6dba9834651769afcf")
        with tarfile.open(archive) as stream:
            stream.extractall(DATA / "llama-vulkan", filter="data")
    elif args.command == "model-start":
        return start_model(args.cpu)
    return 0


if __name__ == "__main__":
    sys.exit(main())
