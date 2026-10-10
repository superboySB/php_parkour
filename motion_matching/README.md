# Motion matching

[Project overview](../README.md)

Generate parkour motion/terrain datasets for the Unitree G1.

To skip generation, use the [prepared example motion/terrain bundles](../wbt_training/README.md#example-motionterrain-datasets)
and follow the [teacher-training instructions](../wbt_training/README.md#train-a-teacher).

## Setup

The research branch uses the unified Docker from [note.md](../note.md).
From the PHP checkout root on the host:

```bash
bash scripts/research/docker.sh build
bash scripts/research/docker.sh gui
python3 scripts/research/verify_assets.py
docker exec -it php-parkour-research bash
# The remaining commands run inside this Docker shell.
source /opt/php/bin/activate motion
mkdir -p /outputs/manual-motion
cd /outputs/manual-motion
```

All project packages are already installed inside Docker. The image sets
`PHP_MOTION_DATABASE_DIR=/data/assets/databases`; generated files here remain
under the persistent `/outputs/manual-motion/` directory. GUI mode requires
the host display configuration described in note.md.

The downloader checks the archive and every extracted file against the SHA-256
manifest in [release-assets.json](../release-assets.json).

The download provides the motion-matching databases and source terrains.
Generation uses these to create the motion/terrain datasets for RL training.
Robot models and required meshes are included in the Python package.

## Generate and inspect

```bash
python -m motion_matching.run --mode generate --scenario high_speed_climb_76
python -m motion_matching.motion_visualizer \
    --motion-file motion_matching_results/high_speed_climb_76
```

Generated motions are exported at 50 FPS. Each motion has paired terrain files
in `motion_matching_results/<scenario>/`:

| File | Contents |
|---|---|
| `*_motion.npz` | Reference motion and per-frame direction commands, when supplied |
| `*_terrain.npy` | Box obstacles with randomized terrain variants |
| `*_terrain.obj` | Terrain mesh for visualization |

Choose a scenario from [builtin.py](motion_matching/scenarios/builtin.py), such
as `low_speed_step`, `high_speed_climb_76`, or `random_locomotion`. Open the
visualizer's URL to inspect a generated motion.

For interactive motion matching, run `python -m motion_matching.run`.
Interactive keyboard control needs Tkinter.

## Prepare a local training bundle

Convert generated tracking motions into native Holosoma data and copy their
paired terrain files. These commands run in the Docker shell above:

```bash
train-python -m wbt_training.training_runs.motion_convert \
    /outputs/manual-motion/motion_matching_results/high_speed_climb_76 \
    /outputs/manual-native/high-speed-climb-76
cp /outputs/manual-motion/motion_matching_results/high_speed_climb_76/*_terrain.npy \
    /outputs/manual-native/high-speed-climb-76/
```

For [training](../wbt_training/README.md#train-a-teacher), use the complete local
bundle as the registry. No online account or upload is required; TensorBoard
records training curves locally. The directory converter handles NPZ files;
the copy command preserves terrain pairing.

```bash
REGISTRY=file:///outputs/manual-native/high-speed-climb-76
```

## Add your own motions or scenarios

For a 30 FPS G1 source clip (`qpos` shaped `(T, 36)` in
`[root_quat_wxyz, root_pos, dof29]` order), build a database with its terrain:

```bash
python -m motion_matching.generate_database \
    --motion-file /path/to/source.npz \
    --terrain-file /path/to/box.obj \
    --fps 30 --output database_g1_skill_name.bin
python -m motion_matching.play_database --database database_g1_skill_name.bin
```

Set `--fps` to the source clip's frame rate. The builder resamples the motion to
60 FPS and writes the database to the cache.

Register new skills in
[skill_registry.py](motion_matching/scenarios/skill_registry.py), compose
scenarios in [builtin.py](motion_matching/scenarios/builtin.py), and run them
with `--mode generate --scenario <name>`.
