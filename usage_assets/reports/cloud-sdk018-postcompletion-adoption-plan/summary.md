# Post-completion cloud default SDK0.1.8 adoption — plan only

The complete SDK0.1.8 image is already loaded on Tencent, but the default cloud environment has **not** adopted it. The retained remote `php-parkour:research` tag and `php-parkour-cloud-research` container still use image631. This is intentional while the original official training and existing 888-source watcher run. No SSH, Docker, network, daemon, GPU or migration command was executed in this audit; only local source and saved receipts were read. Production, main docs, active cohorts and waiter contracts are unchanged.

The saved image inspect recomputes Config/RootFS SHA `9dc4e5696747951769505625a96dddc5bfd3240e3ff504db7dbef4526b2d8395`. The successful upload receipt records local ID `2be18521015b…`, remote ID `fdfb7221af88…`, and an already-loaded 10,897,464,145-byte archive with SHA `03fbce4defd450f365e7654de7fef6308d390301df520562f5b0fb9e1d1f9280`. Different image IDs after Docker-store conversion do not imply different contents. The initial upload helper's failed receipt is preserved; the later independent verification passed. All 11 published upload raw-copy hashes were rechecked locally in this audit.

The latest saved live snapshot used here is 2026-10-10 11:14:07 UTC: original cloud CID `f1f07942…`, image631, StartedAt `2026-10-10T04:01:22.880471283Z`; fresh629 was still running (195 completed/1 running/433 planned). The local delivery waiter's first actual poll at 11:03:24 UTC was waiting, with 16 stage blockers and no CPU-ready receipt. These are historical saved observations, not a new live status query.

## Concrete integration findings

- [cloud.py](../../../scripts/research/cloud.py) uses the fixed `php-parkour-cloud-research` name and the local/remote `php-parkour:research` tag. `upload_image()` retags remote IMAGE after checking the archive/layers (lines154–214). The candidate upload deliberately overrode IMAGE to a separate tag. Retagging alone does not change existing container image IDs or complete default-container adoption.
- `deploy()` refuses any exact existing name, including a stopped container (`docker ps -aq`, lines230–232). It has no `--name`/`--image` option or official-training/watch completion gate. After terminal verification the old CID must be retained under another name before using this entry point.
- `deploy()` then freezes/syncs source and assets, verifies release assets, rechecks smallest idle GPU, and runs the immutable returned remote image ID (lines233–259). With the new candidate promoted first, `upload_image()` should find matching contents and return `already_present=true`; it need not rebuild or transfer the archive again.
- Default deployment writes local and remote `deployment.json` and the asset-verification report. Archive those operational records byte-for-byte before adoption. Never rewrite official manifests, original model/export files, coverage selection/attempts or their receipts. `sync` creates a new source tree; it must not replace source0093 or monitor source02bc.
- Default source/assets/output/cache/log mounts are RW and default networking is host. This differs from the isolated RO-source/native cohorts. Adoption should preserve the default launcher contract, and must not silently alter any frozen888/final58 image/source/plan. Future RO-source Isaac evaluation still needs its separate 35-file RW robot-assets override.
- Doctor is `verify_runtime.py` through `docker.sh doctor` locally or `cloud.py exec` remotely. Its `passed` flag checks imports and optionally CUDA availability; it does **not** assert SDK0.1.8 or exactly one CUDA device (verify_runtime.py63–65). Check these fields explicitly and compare all three runtime versions against the published local SDK018 doctor. GPU model/name naturally differ between hosts.
- `cloud.py pull` copies the whole output tree. Do not use it for final delivery; the existing waiter must retain its selective four-ONNX/28-JSON flow. Default-container adoption is independent of that flow.

## Gates before the first mutation

1. Original official16 manifests passed and canonical provenance validated: teachers final iter19999/4096env/64variants, pure9999 and finetune29999/2048env/3variants; ordered teachers/registries, final outputs and SHA records match. Reuse the frozen monitor's standard-library `inspect_artifacts` gate plus its **existing actual Docker CPU-ready** scientific receipt for all seven PTs. Do not load Torch/NumPy on either host. Observe the exact final driver marker, no live train/eval/export children, and released official lock.
2. Existing source02bc watcher has actual terminal accounting: three unfiltered296 plans/888 unique attempts, selection and CPU-ready identity, all raw evidence SHA checked by frozen `verify_finished_batch`, and stopped CPU/GPU containers with matching exits. Default successful adoption waits for `completed`/exit0. A terminal `execution_failed` is retained failure evidence requiring a separate review, not permission to claim success or restart training.
3. Exact watch PID4074213/birth702550493 has exited; a reused PID is not signalled. Both global `.posttrain-coverage.lock` and `official-acceptance.lock` are available. Hold them across adoption, so another driver/watch cannot arm during the handoff. Run the monitor's lock-probing `process_gate` **before** taking this operator lease; while holding it, recheck processes/marker/provenance directly rather than treating your own held lock as an external blocker.
4. Freshly verify local research ID2be and remote candidate immutable IDfdfb both reproduce9dc4. Check exact old CID/image/StartedAt/labels/sorted mounts and only sleep/TensorBoard remain; preserve all other containers. No concurrent build, retag or deployment. Preserve the old631 image tag/CID and both original source trees, plus all official/coverage evidence.

These gates are not currently satisfied by the saved running snapshots. Do not execute the following now.

## Candidate commands after those gates (not executed)

The full argv arrays and per-command requirements are in `report.json`. A root operator can hold the existing locks in one dedicated remote shell through the adoption/doctor steps:

```bash
ssh -tt -p 22 -o BatchMode=yes -o PasswordAuthentication=no tencent-231 \
  'flock -n /diff/dzp_is_sb/php-parkour-research/outputs/.posttrain-coverage.lock flock -n /diff/dzp_is_sb/php-parkour-research/outputs/official-full/official-acceptance.lock bash --noprofile --norc'
```

Archive previous local/remote deployment, image-transfer and asset-verification records with their SHAs first. In another operator terminal, after fresh identity/fingerprint checks and while that lease remains held:

```bash
ssh -p 22 -o BatchMode=yes -o PasswordAuthentication=no tencent-231 \
  'docker tag sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd php-parkour:research-sdk016-retained'
ssh -p 22 -o BatchMode=yes -o PasswordAuthentication=no tencent-231 \
  'docker stop --time 20 f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db'
ssh -p 22 -o BatchMode=yes -o PasswordAuthentication=no tencent-231 \
  'docker rename f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db php-parkour-cloud-research-sdk016-official-retained-01'
ssh -p 22 -o BatchMode=yes -o PasswordAuthentication=no tencent-231 \
  'docker tag sha256:fdfb7221af88ad70236d8b40c463008677f9a622343972394efa99055ad71df3 php-parkour:research'
python3 scripts/research/cloud.py --host tencent-231 --remote-root /diff/dzp_is_sb/php-parkour-research deploy
python3 scripts/research/cloud.py exec /opt/php/bin/train-python scripts/research/verify_runtime.py \
  --require-gpu --output /outputs/cloud-sdk018-default-adoption-01/runtime.json
```

Every name/output here must be fresh; abort if a retained name or new report path already exists. Recheck stopped state before rename. The deploy entry point selects the smallest currently idle **nvidia-smi index**, then maps its UUID; it must not infer index from Linux minor number or forcibly reclaim a busy card. Record new CID, actual immutable image/fingerprint, source manifest/tree/Githead, all asset verification, exact UUID/device visibility and actual doctor output. The doctor must show SDK0.1.8 in train and inference, `cuda_available=true`, `cuda_devices=1`, and the same three-environment dependency versions as local. Compare local research tag before/after deploy as well.

At this point both default tags and default containers can be called unified **only after** those actual receipts pass. Preserve the old CID stopped, with all original binds intact; do not `rm`, prune, restart the official driver or re-arm its monitor. Historical monitor replay must explicitly address that retained old CID/image, not mistake the new default container for the original run. TensorBoard6006 may be restored separately on the new container against existing official logs after confirming its port is free; this neither resumes training nor changes its evidence.

If a completion/provenance/identity/GPU/doctor check fails, stop migration for review and preserve every raw record. Do not automatically resume/retry/restart training or reinterpret failures. A newly created unhealthy default container may be stopped only after verifying its own exact identity; old image/container/source remain available. The existing local waiter and all frozen native cohorts are untouched.

No host/server Conda, pip, apt or new environment is needed. Existing Docker, SSH, rsync, gzip, flock and Python standard libraries are sufficient. This plan and a future doctor do not constitute a new remoteSDK018 Isaac-training/DDS/native validation run; those scopes remain separate from default environment adoption.
