# Canonical SDK018 recipe proposal

Status: four-file ignored proposal only. No tracked file or existing image/container/tag changed, and no canonical image built.

Apply candidate.patch only after root approval. It changes the existing single Dockerfile to install Holosoma [booster] plus explicit far-unitree-sdk==0.1.8 in train and inference; both runtime constraints pin0.1.8. The fixed Holosoma submodule keeps its upstream optional [unitree]==0.1.6 declaration. Selecting that extra together with explicit0.1.8 is unsatisfiable.

Actual CPU proof: a new owned runc/network-none/read-only-root container of caf61487… exited0, no GPU requests, no SDK import/constructor or DDS. Both [booster]+explicit018 installed-environment pip dry-runs passed with empty install lists; both original [unitree,booster]+018 were correctly rejected as ResolutionImpossible. Actual train/motion/inference pip-freeze raw bytes were collected afresh and match the prior candidate records exactly. Every constraint name/version was checked against actual package metadata (117 train-added,82 motion,66 inference).

runtime-locks.json source_image is the actual caf61487… lock provenance, not a future canonical image. New freeze SHA values are actual measured bytes. Train/inference SDK lines are direct local-wheel URIs; a future index install can legitimately render ==0.1.8. Preserve new final raw freeze and compare package versions/SDK binary hashes rather than copying or inventing a final freeze SHA. Motion constraint/freeze bytes remain unchanged. Existing build-backend locks remain unchanged; prior fresh full resolver proof concerned016, so it is not re-labelled as018 proof.

After approved application, root can build locally with network and existing caches using the same recipe and a fresh candidate tag:

```bash
docker build --progress plain \
  --build-arg PHP_REVISION=<APPROVED_ROOT_COMMIT> \
  --build-arg HOLOSOMA_REVISION=<FIXED_SUBMODULE_COMMIT> \
  --build-arg PHP_SOURCE_DIRTY=false \
  --tag php-parkour:research-sdk018-canonical-candidate \
  --file docker/Dockerfile .
```

This command has not run. Do not overwrite the existing research tag until the new image and native regression pass. Capture Docker build argv/log, exact Config ID/RootFS layers/source commit, all three actual /opt/php-build/*.freeze.txt and installed SDK module/bundled library hashes. Compare the approved018 cp311/cp312 wheel contents, version018 in train/inference, no SDK in motion, Torch2.7/cu128 and NumPy1.26.4 train, NumPy2 inference/motion, Booster0.1.1, and preservation of unchanged distributions. Old official training/watch stay on their original image/source bind.

The two approved018 wheel hashes are1960dc533c25455a92d91e221ab7fdd22051a8da0d3db673842696ecf6a6aaa6 (cp311) and328060abe544f841f3058e763b32514afb3468e17fadfac512df92e02bcfb9d1 (cp312); both are x86_64 manylinux2.31. Expected installed extension SHA:9304320e194ca6fb0bc4f85699a533bcc3051f577bd823914903aedc9b1b0926 train, fdedc667b19b8257c4a2e2cc70d8a99c65e9425d29366426f73a75ac1d5664d4 inference.

Offline cloud deployment means docker save the complete verified canonical image, hash/archive transfer and docker load with matching Config/RootFS identities, then new separately named containers. It does not mean running pip/apt or rebuilding on the offline server. Dual SDK wheels plus old882/pip HTTP caches do not supply a proven full --no-index wheelhouse or apt archive; complete offline bootstrap is not claimed. No second long-lived Dockerfile/stage path is proposed.
