V3 changes only the validator's CPU guard admission: `/proc/driver/nvidia/gpus` visibility remains recorded as `guard.nvidia_proc`, and is no longer required to be absent. Read-only host driver metadata can remain globally visible in a container without granting access to GPU devices. The Docker marker, empty `CUDA_VISIBLE_DEVICES`, `NVIDIA_VISIBLE_DEVICES=void`, absence of NVIDIA/render devices, and the host executor's runc/device-request/mount/network/resource checks remain required.

The actual owned CPU01 exited 1 naturally before third-party imports or media children because v2 required this metadata path to be absent. That failed run and frozen v2 are preserved. Scientific inputs remained unchanged. This source preparation is not a successful runtime result.

The validator interface and all scientific/media checks are identical to v2. Invoke the copied host executor with the actual contract SHA and the v3 validator SHA from `source-manifest.json`. `run_owned_cpu.py` and its own source manifest are exact byte copies of v2; no host implementation changed.

`validate-v2-to-v3.diff` contains the complete minimal validator change. `source-manifest.json` binds the prepared sources and records AST admission, copied-host equality and actual failure evidence fingerprints. No candidate source was executed or imported, and no Docker/SSH action occurred during this preparation.
