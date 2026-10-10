"""Import existing callers without constructing any SDK or simulator object."""
import hashlib
import importlib
import json
from pathlib import Path
import sys

runtime, output = sys.argv[1:]
import unitree_interface as sdk

target = {
    "train": "holosoma.bridge.unitree.unitree_sdk2py_bridge",
    "inference": "holosoma_inference.sdk.unitree.unitree_interface",
}[runtime]
module = importlib.import_module(target)
result = {
    "schema_version": 1,
    "runtime": runtime,
    "scope": "imports and static attribute reads only; no SDK/bridge constructors or DDS",
    "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "caller_module": target,
    "caller_file": module.__file__,
    "caller_file_sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
    "sdk_constructor_doc": sdk.UnitreeInterface.__init__.__doc__,
    "create_robot_doc": sdk.create_robot.__doc__,
    "g1_num_motor": sdk.G1_NUM_MOTOR,
    "g1_hg_config": {n: getattr(sdk.G1_HG_CONFIG, n) for n in ("num_motors", "name")},
    "dds_config_api_version": sdk.DDS_CONFIG_API_VERSION,
}
if runtime == "inference":
    result["python_wrapper_lifecycle_api"] = [
        n for n in ("close", "stop", "shutdown", "join", "destroy")
        if hasattr(module.UnitreeInterface, n)
    ]
    assert not result["python_wrapper_lifecycle_api"]
assert result["g1_num_motor"] == result["g1_hg_config"]["num_motors"] == 29
assert result["g1_hg_config"]["name"] == "G1-HG"
Path(output).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"runtime": runtime, "caller_import_passed": True, "g1_num_motor": 29}))
