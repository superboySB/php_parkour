"""Import-only SDK snapshot. Never constructs a robot, initializes DDS or uses CUDA."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import sys


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def public(cls):
    return {key: getattr(cls, key).__doc__ for key in dir(cls) if not key.startswith("_")}


def snapshot(runtime: str) -> dict:
    packages = sorted(
        [{"name": name(d.metadata.get("Name", "")), "version": d.version}
         for d in md.distributions()], key=lambda x: (x["name"], x["version"]))
    # This Python object introspection calls no factory or SDK constructor.
    spec = importlib.util.find_spec("unitree_interface")
    result = {
        "schema_version": 1, "runtime": runtime,
        "scope": "CPU import and public API introspection only; no constructors, DDS, CUDA or simulation",
        "python": platform.python_version(), "executable": sys.executable,
        "prefix": sys.prefix, "base_prefix": sys.base_prefix,
        "platform": platform.platform(), "libc": platform.libc_ver(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "nvidia_visible_devices": os.environ.get("NVIDIA_VISIBLE_DEVICES"),
        "packages": packages,
        "wrapper": {"path": "/opt/php/bin/" + runtime + "-python",
                    "sha256": digest(Path("/opt/php/bin/" + runtime + "-python"))},
        "interpreter_sha256": digest(Path(sys.executable).resolve()),
        "sdk_found": spec is not None,
    }
    if spec is not None:
        import unitree_interface as sdk
        package = Path(sdk.__file__).parent
        binaries = sorted(package.glob("*.so"))
        assert len(binaries) == 1, binaries
        result["sdk"] = {
            "distribution_version": md.version("far-unitree-sdk"),
            "module_file": sdk.__file__,
            "extension_file": str(binaries[0]),
            "extension_sha256": digest(binaries[0]),
            "package_files": [{"path": str(p.relative_to(package)), "bytes": p.stat().st_size,
                               "sha256": digest(p)} for p in sorted(package.rglob("*"))
                              if p.is_file() and "__pycache__" not in p.parts],
            "module_public_names": [n for n in dir(sdk) if not n.startswith("_")],
            "interface_public_api_docs": public(sdk.UnitreeInterface),
            "create_robot_doc": sdk.create_robot.__doc__,
            "factory_docs": {n: getattr(sdk.UnitreeInterface, n).__doc__
                             for n in ("create_custom", "create_g1", "create_go2", "create_h1", "create_h1_2")},
            "robot_types": {n: int(getattr(sdk.RobotType, n)) for n in dir(sdk.RobotType)
                            if n.isupper() and isinstance(getattr(sdk.RobotType, n), sdk.RobotType)},
            "message_types": {n: int(getattr(sdk.MessageType, n)) for n in dir(sdk.MessageType)
                              if n.isupper() and isinstance(getattr(sdk.MessageType, n), sdk.MessageType)},
            "explicit_lifecycle_api": [n for n in ("close", "stop", "shutdown", "join", "destroy")
                                       if hasattr(sdk.UnitreeInterface, n)],
        }
        libs = package.parent / "far_unitree_sdk.libs"
        result["sdk"]["bundled_libraries"] = [{"name": p.name, "sha256": digest(p), "bytes": p.stat().st_size}
                                               for p in sorted(libs.glob("*")) if p.is_file()]
    return result


def compare(old: dict, new: dict) -> dict:
    failures = []
    def check(condition, description):
        if not condition:
            failures.append(description)
    for field in ("runtime", "python", "executable", "prefix", "base_prefix", "libc", "wrapper", "interpreter_sha256"):
        check(old[field] == new[field], "changed " + field)
    without_sdk = lambda x: [p for p in x["packages"] if p["name"] != "far-unitree-sdk"]
    check(without_sdk(old) == without_sdk(new), "non-SDK distributions changed")
    if new["runtime"] == "motion":
        check(not old["sdk_found"] and not new["sdk_found"], "motion unexpectedly has SDK")
        check(old["packages"] == new["packages"], "motion package set changed")
    else:
        check(old["sdk_found"] and new["sdk_found"], "SDK import missing")
        check(old["sdk"]["distribution_version"] == "0.1.6", "baseline SDK is not 0.1.6")
        check(new["sdk"]["distribution_version"] == "0.1.8", "candidate SDK is not 0.1.8")
        check(set(old["sdk"]["interface_public_api_docs"]) <= set(new["sdk"]["interface_public_api_docs"]), "removed public interface method")
        check(old["sdk"]["robot_types"] == new["sdk"]["robot_types"], "RobotType values changed")
        check(old["sdk"]["message_types"] == new["sdk"]["message_types"], "MessageType values changed")
        for factory in ("create_robot_doc",):
            doc = new["sdk"][factory] or ""
            check("network_interface: str" in doc and "robot_type:" in doc and "message_type:" in doc,
                  "create_robot positional parameters differ")
            check("MessageType.HG" in doc and "dds_config" in doc and "None" in doc,
                  "create_robot defaults do not match expected HG + dds_config None")
        check(not new["sdk"]["explicit_lifecycle_api"], "unexpected lifecycle API; reassess plan")
    result = {"passed": not failures, "failures": failures,
              "scope": "Import-only ABI/public API/package identity; not a native robot lifecycle test",
              "removed_methods": [] if new["runtime"] == "motion" else sorted(set(old["sdk"]["interface_public_api_docs"]) - set(new["sdk"]["interface_public_api_docs"])),
              "added_methods": [] if new["runtime"] == "motion" else sorted(set(new["sdk"]["interface_public_api_docs"]) - set(old["sdk"]["interface_public_api_docs"]))}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, choices=("train", "inference", "motion"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    result = snapshot(args.runtime)
    if args.baseline:
        result["comparison"] = compare(json.loads(args.baseline.read_text()), result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"runtime": args.runtime, "sdk": result.get("sdk", {}).get("distribution_version"),
                      "distribution_count": len(result["packages"]), "comparison": result.get("comparison")}))
    if result.get("comparison", {}).get("passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
