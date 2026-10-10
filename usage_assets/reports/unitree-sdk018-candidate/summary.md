# SDK0.1.8 independent candidate — CPU verification

Candidate image: `php-parkour:research-sdk018-pilot`  
Config ID: `sha256:caf61487b69ce478980b3bf9df38a7f1fcaaae4b109d971dfbea10b09bf441aa`  
Base config ID: `sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f`  
Result: offline build exit0; independent **network-none, runc, no GPU** container exit0. No robot, bridge or simulator object was constructed; no DDS or simulation run was started. This proves import/API/package compatibility, **not** that native shutdown or629 execution has been repaired.

| Runtime | Python / prefix | SDK before→after | Distributions | Verification |
|---|---|---|---|---|
| train | 3.11.13, `/isaac-sim/kit/python` (not a venv) | 0.1.6→0.1.8 |357| SDK and actual bridge module import; old factory positional parameters/default messages retained; G1 count29 |
| inference |3.12.3, `/opt/php/envs/inference` |0.1.6→0.1.8|68| SDK and actual Python wrapper import; same factory/default checks; G1 count29 |
| motion |3.12.3, `/opt/php/envs/motion` |absent→absent|84| Full pip-freeze bytes unchanged |

All non-SDK distribution names/versions match baseline. All three wrapper and interpreter SHA256 fingerprints match. The candidate inherits all44 base RootFS layers unchanged and adds5 layers. The unchanged motion claim covers package freeze/fingerprints and inherited base layers; no separate full-file hash of the entire motion venv was taken. Old `php-parkour:research` tag, running research container image ID, both original SDK0.1.6 metadata and both original extension SHA256 were checked after candidate creation and remain unchanged (`original-sdk-unchanged.json`).

## Official offline inputs

The [official0.1.8 PyPI release](https://pypi.org/project/far-unitree-sdk/0.1.8/) supplies manylinux2.31 x86_64 wheels compatible with the image's glibc2.39. Downloaded wheel SHA256 and installed extension match were checked:

| Wheel | Bytes | SHA256 |
|---|---:|---|
| `far_unitree_sdk-0.1.8-cp311-cp311-manylinux_2_31_x86_64.whl` |11880816|`1960dc533c25455a92d91e221ab7fdd22051a8da0d3db673842696ecf6a6aaa6`|
| `far_unitree_sdk-0.1.8-cp312-cp312-manylinux_2_31_x86_64.whl` |11880630|`328060abe544f841f3058e763b32514afb3468e17fadfac512df92e02bcfb9d1`|

Train installed extension: `9304320e194ca6fb0bc4f85699a533bcc3051f577bd823914903aedc9b1b0926`.  
Inference installed extension: `fdedc667b19b8257c4a2e2cc70d8a99c65e9425d29366426f73a75ac1d5664d4`.

The factory keeps `(network_interface, robot_type, message_type=HG)` and adds keyword-only `dds_config: str | None = None`. Existing static robot factories keep their previous message defaults. Both wheel imports add `enable_motion_switcher_responder`; neither SDK nor Python wrapper adds `close/stop/shutdown/join/destroy`. The upstream destructor fix is documented with immutable sources and hashes in `../unitree-lifecycle-independent/report.md`. Default `dds_config=None` takes the old `Init(0,nic)` path, but new DDS guards/responder support still need later native regression.

## Reproduce this isolated build

The exact standalone recipe is `context/Dockerfile`; source inputs are bounded by `build-context-manifest.json`. Its context contains only two official wheels, their SHA manifest, the import verifier and three baseline JSON snapshots; it contains no workspace source tree, `.git`, secrets or outputs. The build argv is in `build-launch.json`:

```bash
docker tag sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f php-parkour:sdk018-base-88254ac0b90a
docker build --network none --progress plain \
  --build-arg BASE_IMAGE=php-parkour:sdk018-base-88254ac0b90a \
  --tag php-parkour:research-sdk018-rebuild \
  --file outputs/research/unitree-sdk018-candidate/context/Dockerfile \
  outputs/research/unitree-sdk018-candidate/context
```

Before retagging/rebuilding, verify the base ID and use a fresh candidate tag. Each pip install uses local hash-verified wheels with `--no-index --no-deps --force-reinstall`, in new image layers only. The independent runtime argv/config/exit receipt is `runtime-launch.json`, `runtime-container.json`, `runtime-status.json`; it uses fixed image config ID, `--network none --runtime runc`, no device requests, empty CUDA visibility, and only the owned audit directory bind. `runtime-*.json`, `import-caller-*.json` and matching freeze files retain actual observations. No scientific host/server package was installed.

The original project extras/constraints and base `/opt/php-build` records still specify SDK0.1.6; they are intentionally untouched. This overlay is outside the frozen foundation and should not be described as its official lockfile build. New actual package/API records are retained separately here; full dependency-resolution/pip-check validation was not added or claimed.

## Preserved diagnostic attempts and limitations

`baseline-attempt01/` retains a verifier-only failure caused by selecting all `.so` files, including bundledDDS libraries. The corrected selector chooses the CPython extension. `baseline-attempt02/` retains an earlier successful snapshot. `build-attempt01/` retains an ABI-check tool failure: a JSON list was compared with a fresh Python tuple for `libc`; normalizing the new field to a list corrected it without changing SDK compatibility logic. `runtime-attempt01/` retains successful three-runtime ABI checks followed by a diagnostic command quoting error through Isaac `python.sh -c`; final import checks use a saved Python file and the final complete container exits0. No failed evidence was overwritten. The final recipe emits an ARG-without-default warning; its recorded mandatory `BASE_IMAGE` argument is valid and verified.

`native-pilot-plan.json` prepares a new isolated lifecycle cohort for the two failed configurations, including explicit final worker returncodes, PID mappings, fresh500tick/10s body evidence and decoded video. Root must authorize and schedule that later native work; it was **not executed** here. Old629 failures remain failures and old completed-case worker-exit evidence is not upgraded by this CPU candidate.
