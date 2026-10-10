# Native GUI operator attempt — prepared, not executed

This directory is ignored research tooling. No native GUI/DDS/GPU/X server was started while preparing or checking it. CPU checks are not native GUI acceptance.

The reviewed operator command, to be run by root only after its current native batch releases the shared host GPU lock, is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  outputs/research/native-keyboard-gui-runner-proposal/host_runner.py run \
  --plan /home/dzp/projects/php_parkour/outputs/research/native-keyboard-gui-prepared-final/cohort/plan.json
```

The fixed plan is `37817077d9ef078b368f793dffd3caf68539392244ff109c2fa429d1421834c1`. It selects exactly canonical image `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f` and GPU `GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25`. Preparation copied all 3298 actual files in the immutable build context; its 3309-file snapshot adds nine audit helpers and two exact original entry copies. Plan fingerprints cover the full copied source and local released ONNX pair, including both diagnostic entry overlays.

The initial `native-keyboard-gui-prepared-01` is CPU development history, never a native attempt. The final prepared attempt has no launch receipt or output files. The operator refuses to overwrite or rerun an attempted directory; failures require a new prepare/reviewed plan rather than evidence edits.

## What an actual operator run does

1. Validate all prepared bytes, exact image/RootFS, local Docker endpoint, owner UID and current helper hashes. Take exclusive nonblocking locks on the shared `.local-native-GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25.lock` and its own display lease. Reject compute processes on that GPU and an occupied `:91` socket/lock.
2. Create a new Xephyr `:91`, private 0600 Xauthority with an unlogged cookie, private root ownership token, and XTEST/RECORD/GLX checks. No key is sent to the parent display. The parent display is only the existing X server needed to host the nested Xephyr window.
3. Create a new labelled exact-CID Docker container with private PID/IPC, network none, init, 8 GiB SHM, source/models/cohort RO, outputs/cache RW, only the private display socket and auth file. It never execs/stops an existing container. Repeat CPU import and exact CLI parsing before spawning native objects. A separate observer records only this CID's cgroup, NSpid, birth and command_writer threads.
4. Start byte-exact `run_php_sim.sh` and `run_php_inference.sh` in separate actual foreground PTYs. The simulator uses CPU physics, real private GLFW MuJoCo window, 500 Hz physics/50 Hz policy, plane geometry, mounted D435i SHM producer and actual released ONNX models. The unchanged wrapper already selects `terrain-load-step`; its mesh is explicitly overridden by `--terrain.terrain-term.mesh-type PLANE` (a second terrain subcommand and lowercase enum both fail native Tyro parsing).
5. Observe original native methods after each original call, without replacing actions/providers/key mappings/SDK logic, refreshing state caches or adding heartbeat polls. Wait for three advancing original liveness sequence observations and an actual two-second initial simulator settle. No claim of feet-contact calibration is made.
6. Place only the owned native spectator window and audit terminal apart inside the private display. Genuine XTEST events focus only identified owned XIDs; the Tk audit terminal forwards actual KeyPress characters into the native inference PTY, while original pynput sees actual held direction down/up. Require native X11 hold-to-move log and observed control-loop state changes.
7. Exercise MuJoCo `8/9`, terminal `]`, recording `c`, held `w` low command1, `c` manual save, `=` speed mode, `c`, held `w` high command6, `o` damping plus native autosave, then `i` stiff hold. Require each original-state acknowledgement. Capture exact owned MuJoCo/terminal drawable PNGs. Preserve raw PTY bytes/text and observers. Validate two original NPZ recordings: float32 T×36 quaternion-first inference qpos, T×15 one-hot command and scalar integer FPS50; require code1/code6 in the actual clips.
8. Interrupt the exact observed birth-verified native Python PID with SIGINT, first inference then simulation. This leaves waiting Bash alone and follows each original KeyboardInterrupt handler. Passive viewer close alone is insufficient because `DirectSimulation.run` is `while True`. Require original main returned, actual wrapper rc0, no live owned group, no fatal/traceback text, and original MP4 saved/full decoded with CPU ffmpeg. Never normalize 130/1/nonzero to0. Esc is not used as policy stop.
9. Release held keys in finally. Birth-verified private groups get bounded TERM→KILL only on abnormal cleanup, which fails native acceptance; an unknown group is never signalled. Stop only the exact new labelled container; reap own observer/docker-client groups; stop only own Xephyr birth group. A cache directory is retained but excluded from the evidence manifest, as is the ephemeral auth cookie. All source and raw success/failure evidence are retained with SHA256/bytes.

`outputs/summary.json` is the GUI workflow terminal result. `host/launch-receipt.json` binds actual CID/image/launch/host identities and all cleanup. `manifest.json` hashes the final raw evidence. Successful completion proves one plane keyboard/GUI interface workflow, not skill success, all terrains, stable locomotion quality or hardware deployment. Diagnostics add I/O timing overhead; this is not a performance benchmark.

## CPU verification completed

- `cpu-tests-final/tests.xml`: 19 tests passed, 0 failures/errors. Meaningful guard checks cover input tamper/traversal/symlink, private display/XID/foreign client refusal, exact source/namespace/image bind args, changed birth no signal, partial-start I/O cleanup registration, real nonzero not rewritten, SHA-bound host/native mapping, readonly simulator state and diagnostic original-call/return parity.
- `cpu-tests-final/report.json`: includes an actual ordinary stdlib child PTY receipt/raw text with foreground PID=PGID=SID and actual `]c` read, original KeyboardInterrupt handler and exit0. This is not a policy/native process.
- `cpu-imports-final/{simulator,inference}-cpu-preflight.json`: real canonical new runc/network-none/noGPU containers imported 151/52 source modules, loaded unitree bridge metadata, parsed the exact real native CLI and installed the diagnostic method wrappers. No Robot/SDK, policy, viewer, simulation object or listener was constructed.
- `cpu-imports-final/launch.json` binds exact Docker argv and raw log fingerprints. PYNPUT dummy is used only for these CPU import containers; the actual operator run does not set it and demands real hold-to-move.
- The native key observations, real MuJoCo window screenshots, real two recording clips, actual rendering compatibility and all-worker normal completion remain pending operator execution. A missing gate must produce failed evidence.
