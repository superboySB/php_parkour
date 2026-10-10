# PHP sim2sim with the RealSense D435i student

[Project overview](../README.md) · [Docker setup](../note.md) · [Actual results and videos](../usage.md)

Run the depth policy on the half-sphere-hand Unitree G1 with 29 actuated joints.
A student consists of two matching local files, `depth_backbone.onnx` and
`student.onnx`: the backbone encodes D435i depth, and the student combines its
latent with proprioception and a direction command to produce joint targets.

The `research` branch runs simulation, inference, training and export inside
one Docker image. Follow [note.md](../note.md) to clone this branch, build the
image and download/check all assets. Project Python dependencies are installed
in the image. Cloud execution uses the same image, local files and TensorBoard.

## Get Holosoma and install the runtimes

The pinned [Holosoma submodule](../thirdparty/holosoma) and its runtimes are
included by the [Docker build](../docker/Dockerfile). After initial setup, run
these checks **on the host, from the PHP repository root**:

```bash
git submodule update --init --recursive thirdparty/holosoma
python3 scripts/research/verify_assets.py --verify-only
test -n "$DISPLAY" && test -f "$XAUTHORITY"
bash scripts/research/docker.sh gui
bash scripts/research/docker.sh doctor --require-gpu
```

Select GUI mode before starting jobs: `docker.sh gui` recreates this project's
container. It uses the existing X11 session and Xauthority cookie. See
[note.md](../note.md) for first downloads, headless startup and troubleshooting.

The container is `php-parkour-research`, with repository `/workspace/php_parkour`,
results `/outputs` and assets `/data/assets`. Both launchers must run in this
same container. Simulation uses `train-python`; inference uses the isolated
`inference-python` environment. `PHP_DOCKER=1` selects these image runtimes.

The native Unitree SDK DDS bridge uses interface `lo`. The simulator publishes
D435i depth to `depth_img_shm`, with shape `(1, 1, 58, 87)`. Both processes share
the container's private `/dev/shm`; keep the provided Compose IPC configuration.
These native transports and policy implementations are used by the tests below.

## Start simulation and inference

Use two host terminals. End any previous simulation and inference first,
because the simulator launcher recreates `depth_img_shm`.

```bash
# Host terminal 1
docker exec -it -w /workspace/php_parkour php-parkour-research bash ./run_php_sim.sh
```

The launcher selects the half-sphere-hand G1, D435i camera, local DDS bridge,
500 Hz physics and Holosoma's bundled stepped course. Wait for:

```text
[DepthShmPlugin] created 'depth_img_shm' (20184 bytes) shape=(1, 1, 58, 87)
```

Then start inference with the validated public pair:

```bash
# Host terminal 2
docker exec -it -w /workspace/php_parkour \
  -e BACKBONE=/data/assets/student/depth_backbone.onnx \
  -e STUDENT=/data/assets/student/student.onnx \
  php-parkour-research bash ./run_php_inference.sh
```

Wait for the policy's attachment message:

```text
[DepthShmSensor] attached to 'depth_img_shm' shape=(1, 1, 58, 87)
```

Both models must belong to the same checkpoint/export. For your own pair, set
`BACKBONE` and `STUDENT` to their actual mounted paths. Host `outputs/research/`
is visible as `/outputs/`; validated assets are visible as `/data/assets/`.

To change terrain, append `terrain:terrain-locomotion-plane` to the simulation
command for a plane, or
`--terrain.terrain-term.obj-file-path /outputs/path/to/course.obj` for your OBJ.
Replace that example path with an existing mesh. Native CLI overrides are
forwarded by the launcher. Loading a mesh does not verify policy traversal.

## Control the robot

Lower the gantry with `8` in the MuJoCo window until the feet reach the ground,
then remove it with `9`. Press `]` in the policy terminal to start the policy.
`o` enters damping mode; `i` returns to the stiff startup pose. Press
`Backspace` in the MuJoCo window to reset the environment.

| Direction or action | Policy-terminal key |
| --- | --- |
| Forward / backward | `w` / `s` |
| 45° left / right | `a` / `d` |
| 90° left / right | `q` / `e` |
| Stand | `z` |
| Toggle low/high speed | `=` |
| Start/stop recording | `c` |

Key-release detection requires the display session passed into the GUI
container. The bounded harness supplies commands without manual keyboard
input. Stop both processes before restarting either one.

Native recordings contain `[root_quat_wxyz, zero_xyz, dof29]` and commands:
the SDK supplies zero root-position placeholders. They are not world
trajectories or native training bundles. Use the harness's `trajectory.csv`
for actual simulated world positions. The
[motion conversion guide](../note.md#4-动作匹配可视化与自定义数据) covers the separate
tracking-to-native training conversion.

## Bounded headless checks

Run these on the host from the repository root, with the unified container
running and interactive simulation/inference stopped. Choose fresh empty
output directories. EGL was used for the recorded physical checks;
`--gl osmesa` selects CPU rendering.

```bash
bash scripts/research/docker.sh inference scripts/research/validate_onnx.py \
  --models /data/assets/student --output /outputs/onnx/deploy-new.json
bash scripts/research/docker.sh sim scripts/research/sim2sim.py \
  --models /data/assets/student --terrain plane --commands all --isolate-commands \
  --seed 42 --seconds-per-command 8 --gl egl --output /outputs/sim2sim/deploy-plane-new
bash scripts/research/docker.sh sim scripts/research/sim2sim.py \
  --models /data/assets/student --terrain step --commands 6 \
  --seed 42 --seconds-per-command 20 --gl egl --output /outputs/sim2sim/deploy-step-new
```

The harness runs the native DDS/depth path and ONNX policy at 50 Hz, releases
the gantry, and records physics steps, policy ticks, world trajectories, logs,
MP4 and decoded PNG frames. Each isolated plane command gets a fresh simulation.
`--record-policy` also checks native recording, automatic save on STOP and damping.

Deployed indices are 0–11; slots 12–14 are reserved and only checked as model
inputs. The ONNX validator ran 30 CPU inference cases (15 slots × two synthetic
depth inputs); this does not measure skill success. All 12 plane commands ran
eight simulation seconds without the height/tilt event threshold. Command 11
ended with positive X displacement, so backward tracking was not verified.

The public policy also ran on one representative OBJ from every generated
scene: 17/17 executions completed, with 14 height/tilt threshold events and
three unflagged cases. Each used seed 42 and 500 policy ticks over about ten
simulation seconds. The threshold is pelvis height below 0.4 m or base-up cosine
below 0.35 after gantry release; climbing tilt can trigger it and the robot can
recover. These are neither 14 permanent falls nor course-completion results,
and they do not cover policy behavior on all 629 configurations. Narrow-step
falls, partial climbs and assisted-input failures are retained in
[usage.md](../usage.md#7-mujoco-场景与物理闭环), the
[deployment report](../usage_assets/reports/deployment-summary.md) and the
[17-scene offline video page](../usage_assets/sim2sim/scenarios/playback.html).

## Export a local native checkpoint

The public release provides an ONNX pair, without native teacher/student `.pt`
checkpoints. Export your own student from a real local native `.pt` and the
same five ordered local motion registries used for training. The
[training/export guide](README.md#export-to-onnx) gives the direct command and
checkpoint lookup with explicit `file://` registries.

For an already completed local pipeline student, the independent export is:

```bash
docker exec -w /workspace/php_parkour php-parkour-research \
  bash scripts/research/train_pipeline.sh export --profile official --student-kind finetune
```

This requires its completed stage manifest under
`/outputs/training/official/manifests/`; select the actual profile/student kind
and output directory used by your training. The pipeline supplies ordered
local registries, exports both models and verifies them with ONNX Runtime. It
reports the export directory; use that pair as `BACKBONE`/`STUDENT`. After pulling
cloud results, adjust paths to local mounted files as described in
[note.md](../note.md).

## View offline TensorBoard curves

Training and evaluation write local TensorBoard events. On the host, start
the viewer in Docker:

```bash
docker exec php-parkour-research train-python -m tensorboard.main \
  --logdir /outputs/training --host 127.0.0.1 --port 6006 --load_fast false
```

Open `http://127.0.0.1:6006/`. Use the actual output root if training was written
elsewhere. To inspect the published raw events, use
`--logdir /workspace/php_parkour/usage_assets/tensorboard`. Keep one viewer per
port; cloud viewing uses the SSH port forward in [note.md](../note.md).
The recorded student runs are two-iteration smoke checks and the larger
4096-environment teacher pilot ran 20 iterations. They validate execution and
finite updates, without a convergence or full official-training claim.
