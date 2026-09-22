"""Discover deployed Rime schemes and prepare an isolated profile."""
import json
import os
import re
from pathlib import Path
import shutil

import yaml

from .paths import PROJECT


class RimeLoader(yaml.SafeLoader):
    # Keep YAML 1.2 switch labels such as on/off/yes/no and date-like versions
    # as strings. PyYAML's default YAML 1.1 resolver changes those values.
    yaml_implicit_resolvers = {
        key: [(tag, pattern) for tag, pattern in values
              if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")]
        for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }


RimeLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def source_path():
    return Path(os.environ.get("RIWEN_RIME_SOURCE") or
                Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "ibus/rime").resolve()


def read_yaml(path):
    with Path(path).open(encoding="utf-8") as stream:
        return yaml.load(stream, Loader=RimeLoader)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def discover_schemes(source=None):
    source = Path(source) if source is not None else source_path()
    if not (source / "build/default.yaml").is_file():
        raise ValueError("No deployed Rime configuration. Deploy your Rime schemes first.")
    defaults = read_yaml(source / "build/default.yaml")
    schemes = []
    for file in sorted((source / "build").glob("*.schema.yaml")):
        identifier = file.name.removesuffix(".schema.yaml")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            continue
        config = read_yaml(file)
        engine = config.get("engine", {})
        if not engine.get("processors") or not engine.get("translators"):
            continue
        schemes.append({"id": identifier, "name": config.get("schema", {}).get("name", identifier),
                        "correction": any(value.split("@")[0] == "script_translator"
                                          for value in engine["translators"])})
    if not schemes:
        raise ValueError("No usable deployed Rime schemes found")
    order = [entry["schema"] for entry in defaults.get("schema_list", [])]
    schemes.sort(key=lambda entry: (order.index(entry["id"]) if entry["id"] in order else len(order), entry["id"]))
    previous = None
    if (source / "user.yaml").is_file():
        previous = (read_yaml(source / "user.yaml") or {}).get("var", {}).get("previously_selected_schema")
    return {"schemes": schemes, "selected": next((entry["id"] for entry in schemes if entry["id"] == previous), schemes[0]["id"])}


def selected_scheme(source, requested=None):
    available = discover_schemes(source)
    identifier = requested or os.environ.get("RIWEN_SCHEMA") or available["selected"]
    scheme = next((entry for entry in available["schemes"] if entry["id"] == identifier), None)
    if scheme is None:
        raise ValueError(f"Rime scheme {identifier} is not deployed. Choose an available scheme.")
    return scheme, read_yaml(Path(source) / "build" / f"{identifier}.schema.yaml")


def settings(scheme, schema, port):
    speller = schema.get("speller", {})
    return {"port": port, "min_input": 4 if scheme["correction"] else 1,
            "correction": scheme["correction"] and os.environ.get("RIWEN_CORRECTION") != "0",
            "alphabet": speller.get("alphabet", "abcdefghijklmnopqrstuvwxyz") + speller.get("delimiter", " '")}


def prepare_profile(target, port, source=None, requested=None):
    source = Path(source).resolve() if source is not None else source_path()
    target = Path(target).resolve()
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError("The isolated profile must not overwrite the source profile")
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid RIWEN_PORT")
    scheme, schema = selected_scheme(source, requested)
    engine = schema["engine"]
    engine["processors"] = ["lua_processor@*riwen*processor", *(v for v in engine["processors"] if "riwen" not in v)]
    engine["filters"] = ["lua_filter@*riwen*filter", *(v for v in engine.get("filters", []) if "riwen" not in v)]
    schema["riwen"] = settings(scheme, schema, port)
    # Replace static assets when switching schemes; preserve private learned DBs.
    for name in ("build", "lua", "opencc", "rime.lua"):
        path = target / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)
    for file in target.glob("custom_phrase*.txt"):
        file.unlink()
    (target / "build").mkdir(parents=True, exist_ok=True)
    (target / "lua").mkdir(exist_ok=True)
    for file in (source / "build").iterdir():
        if file.suffix in (".bin", ".yaml") and file.is_file():
            shutil.copy2(file, target / "build" / file.name)
    for name in ("lua", "opencc"):
        if (source / name).exists():
            shutil.copytree(source / name, target / name, dirs_exist_ok=True)
    if (source / "rime.lua").is_file():
        shutil.copy2(source / "rime.lua", target / "rime.lua")
    for file in source.glob("custom_phrase*.txt"):
        shutil.copy2(file, target / file.name)
    aux = target / "lua/aux_code.lua"
    if aux.is_file():
        aux.write_text(aux.read_text().replace("            line = line:match", "            local line = line:match")
                       .replace("for cand in input:iter() do", "for original_cand in input:iter() do\n            local cand = original_cand"))
    shutil.copy2(PROJECT / "rime/lua/riwen.lua", target / "lua/riwen.lua")
    write_json(target / "build" / f"{scheme['id']}.schema.yaml", schema)
    defaults = read_yaml(target / "build/default.yaml")
    defaults["schema_list"] = [{"schema": scheme["id"]}]
    write_json(target / "build/default.yaml", defaults)
    write_json(target / "riwen-profile.json", dict(scheme, pageSize=schema.get("menu", {}).get("page_size", defaults.get("menu", {}).get("page_size", 5))))
    return str(target)
