# Native resume acceptance preparation

Status: **CPU prepared; no native resume or GPU training has been started.**

This is a once-only, root-operated protocol for one locomotion expert. The current pipeline is exercised through its real native subprocesses, while all native learning/load/save code stays unchanged. It cannot establish official five-expert training, convergence, uninterrupted RNG/curriculum restoration, or policy quality.

`readiness.json` binds the final controls, exact source snapshot, CPU evidence and structured root commands. `root-commands.json` contains executable argv arrays, **not an automatically running controller**. Root must review and substitute only its newly created exact CID. Never use an existing container.

## Source and environment

- Canonical SDK018 image: `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`.
- Fixed GPU: `GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25`; the shared mutex is recorded in `root-commands.json`.
- New full source copy:3298 files,653,677,435 bytes. The source manifest preserves each before/after identity.
- The sole overlay is the complete current `scripts/research/train_pipeline.py`29ec49da, replacing frozen5f85596f. The old source remains in the previous pilot and is identified by its original manifest.
- `wbt_training/train_agent.py`a912488c and `thirdparty/holosoma/src/holosoma/holosoma/train_agent.py`3758381c are distinct unchanged entrypoints. All371 native Python package files were compared byte for byte with current source.
- Source, controls and published assets mount read-only; only this preparation’s `run-output-final-frozen` and cache mount writable. The35 original URDF/STL files use the unchanged `runtime_robot_assets.py`445acc80 contract. Generated USD files are permitted solely under its independent RW asset root.
- `HSSIM_PYTHON=/control/train-python-with-robot-assets` forwards registry stdin and other Python calls unchanged. Only the exact `-m wbt_training.train_agent` invocation receives the public `--robot.asset.asset-root /outputs/runtime-robot-assets/robots` override. No algorithm, RNG, load method or optimizer is monkeypatched. The unchanged launcher captures its adapter command before activation rewrites exported `HSSIM_PYTHON` to `/opt/php/bin/train-python`: parent manifest and native exec environment are intentionally validated separately. The actual shell activation regression proves this without starting native training.
- Each native exec receipt stores the original pipeline argv, final exec argv, environment whitelist, source/control SHAs and process birth immediately before exec. Such a start receipt alone cannot establish completion.

## CPU evidence already obtained

Final `cpu-tests/tests-frozen.xml`:33/33 passed,1.05s, in a new runc/networknone container with no GPU request and CUDA hidden. `cpu-tests/frozen-launch.json` preserves exact argv and equal before/after control/test SHAs. Earlier27/29/30/31/32-test and first-preflight evidence remains under its original paths and source snapshot; these counts are not additive.

`run-output-final-frozen/cpu-preflight.json` verifies every3298 sealed source file and actually parses all three native Tyro presets. The public asset override changes exactly one config field. Real `file://` resolution/preprocessing consumes all100 original locomotion clips with one terrain variant and seed42; no simulator or algorithm is instantiated. Temporary motion/OBJ paths in that CPU report are diagnostic outputs of a removed CPU container and are not later training inputs. Future native invocations preprocess the original registry again. The original registry’s complete byte identities are retained in `registry-inputs.json`.

`cpu-tests/actual-existing-optimizer-schema.json` CPU-loads the existing final-smoke teacher/pure/finetune PTs with their known hashes. Their17/16/29 optimizer parameter states all have counts40/16/16. Finetune’s std group has LR0 **and state count16**; pure std is outside its optimizer. These are genuine existing baseline schemas, not resumed runs or single-expert results. CUDA remains uninitialized. A separate actual CPU read also uses native default `torch.load(..., map_location="cpu")` for all three PTs and confirms the CPU RNG state remains unchanged.

## Root execution protocol, not executed here

1. Require the actual previous629 receipt to be completed, driver/CPU-validation return codes0, owned GPU container stopped, native children absent, shared UUID mutex available, and the selected GPU without compute programs. Retain exact UTC/process/container/image/mount/device receipts. Do not stop or alter unrelated resources.
2. Verify the preparation manifest, source3298 hashes, registry files and35-file robot contract. Require `/outputs/resume-smoke`, `/outputs/exec-receipts` and baseline archives absent. The current output contains only CPU preflight/robot assets. Existing native evidence requires a new cohort; do not resume this acceptance controller or overwrite partials.
3. Use the exact `create_argv` in `root-commands.json` to create a unique container. Start and inspect it; require the exact image, name, private IPC/PID/networknone, five mounts with recorded RO/RW flags, `/workspace/php_parkour` working directory, `/bin/bash` entrypoint and one selected GPU UUID. Root owns timeout/cancellation and stops only that CID in `finally` while retaining the mutex.
4. Execute the18 structured step arrays serially; stop on any failure. For teacher, then pure, then finetune: baseline2 → archive original bytes → target4 `--resume` → CPU resume checks → final ONNX checks → completed target4 `--resume --skip-completed` check.
5. Retain the final teacher iter3 SHA before starting either student. Each student baseline/resume uses the same sole teacher source, in source order. Preserve all original files and output partials on any failed check. Root’s terminal receipt must also verify every input/source SHA and its owned container’s actual stopped state.

The commands keep `--profile smoke --skills locomotion --num-envs16`,24 rollout steps,4 mini-batches, teacher5/student2 epochs, save every iteration, one variant, seed42, disabled online logger/TensorBoard enabled, one GPU and student warmup0. They never shorten official training or touch cloud/watch/waiter dependencies. The single-expert scope is deliberate and cannot replace the ordered official five-expert path.

## Required future success evidence

Original baseline PT1, passed manifest, native YAML, matching ONNX export, log and TensorBoard event bytes are copied—not moved—to a fresh archive with SHA/path mapping before resume. Native local checkpoint loading consumes the original path. Resume writes under a different timestamped parent; if that parent collides with the baseline, validation fails. Original PT1 and archived event bytes must remain unchanged.

Native saved `iter` and `iteration` are top-level PT fields, alongside top-level `experiment_config`. Restoring iter1 runs native iterations1,2,3, so target4 ends at3 and repeats the base last iteration. On resume, native `num_learning_iterations` is3 while pipeline `iterations_target` remains4.

The new resumed `model_00001.pt` must already show optimizer40→60 for teacher or16→24 for either student; final PT3 must show100/40. Every parameter state is checked against stable optimizer/group/position identity. Fresh-optimizer fallback fails this check even if the native process exits0. Actor/student/depth and the applicable critic require finite nonzero deltas. Frozen teacher/normalizer tensors remain identical. Finetune’s early PPO coefficient ends at.0003; std LR remains0 and its weights must remain exactly unchanged while its optimizer state advances16→24→40.

The native `train.log` DEBUG sink must name the actual original loaded checkpoint, end with real training shutdown and contain no optimizer-restoration warning. Actual YAML/PT config, manifest source SHA, exec receipt argv and new TB `Loss/*` plus `Train/num_samples` steps1,2,3 must agree. Baseline TB0,1 is retained separately; duplicate step1 is not a continuous uninterrupted schedule.

Final teacher native ONNX must pass12 CPU ORT cases with iteration3/config provenance; each final student auto-export pair must pass30 CPU ORT cases. Student exports have no separate iteration metadata: bind the exact PT3 sibling path and file SHAs. These checks are interface/finiteness checks, not PT/ONNX numerical parity or locomotion quality.

The last skip command is real pipeline execution with a transport guard that refuses any native `-m` child. It must return the verified-already-target4 message while the entire pipeline output tree and native exec receipts remain byte-exact. No old successful eval is used as evidence for restored training.

No future native success is claimed until all these checks, root lifecycle evidence and source/input postchecks actually complete.
