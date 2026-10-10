# Five nondefault teacher presets: SDK018 native reload evidence

All five original smoke teacher checkpoints (iteration1) completed their own Isaac reloading evaluation:16 environments ×100 control steps (2.0 simulated seconds per environment),1 terrain variant, seed42. Four tracking-error metrics each contain1600 finite samples; action and robot-root state probes remain finite. Saved native configs retain each preset's160/449 observations, torso/pelvis anchor and original scaling. This verifies the bounded reload interface and execution, not convergence or skill quality. `quality_verified` remainsfalse.

| Preset | Actor observations | Anchor | Failed episode resets (sum over16env) | Longest linked original video |
|---|---:|---|---:|---:|
| `no-heightscan` | 160 | torso_link | 50 | 0.94s |
| `no-heightscan-noscale` | 160 | torso_link | 51 | 0.62s |
| `no-heightscan-pelvis` | 160 | pelvis | 50 | 0.88s |
| `ref` | 449 | torso_link | 51 | 0.84s |
| `ref-pelvis` | 449 | pelvis | 49 | 0.96s |

There were251 cumulative failed episode resets and0timeouts. A reset count counts terminated episodes across the16 environments; it does not count unique robots or permanent falls. The merged loader reports ID0/one loader entry, which cannot enumerate the100 original locomotion source clips or prove their coverage. All failure counts and original short recordings remain in ignored raw outputs.

The independent CPU-only/no-network/no-GPU audit fully decoded all32 fresh MP4s and verified positive duration (0.02–0.96s);22 are explicitly linked by the quality reports and10 are additional fresh initialization clips. Five actual TensorBoard event files were read, and their17 scalar tags matched the reported finite values. The five selected videos are the longest quality-linked original MP4 per preset (lexical tie break), with unedited midpoint screenshots. They are brief episode recordings, not five continuous2-second demonstrations.

All395 frozen source files,2 preparation helpers,20 original PT/YAML/ONNX/manifest files, and35 original plus35 copied robot assets retain their planned SHA values. Large PTs and ONNX files are referenced by SHA; they are not copied here. Canonical image2be185 was used with a read-only source copy of6cb plus the explicit eval_quality.py exit guard5cbb7f. The guard revision is mounted source provenance, not a claim that the image was rebuilt with that file.

The earlier five attempts failed before physical evaluation because URDF→USD tried writing inside read-only source. Their original logs/receipts remain preserved separately in `../teacher-preset-reload-sdk018-failed-01/`. This fresh v3 uses public `--robot.asset.asset-root /outputs/teacher-preset-runtime-assets-v3/robots`, with35 byte-exact G1 input assets copied to an independent writable data root; generated USD caches are isolated there. Source and original/copy URDF/mesh hashes stayed unchanged.

`review.json` records the independent native config/PT contracts,32 complete video-decode receipts, metric/reset data, actual TensorBoard scalars and all immutable fingerprints. `raw/` contains the five exact quality JSONs, native saved YAML, logs and TensorBoard files. `preparation/` preserves the v3 runner/plan and42-test CPU JUnit; `actual-cpu-preflight/` binds the actual GPU container's preceding CPU-only config parse. No new simulator/GPU/DDS job was started by this post-validation audit.
