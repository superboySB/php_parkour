# Selective final-student transfer: CPU verification and live wait

The new host stdlib helper is frozen after **57/57 Docker CPU tests**. A real read-only SSH `status` returned `waiting`, 16 stage blockers, and `cpu_ready_present=false`. The dedicated local model destination did not exist before or after the check. No model bytes were transferred; no GPU or container launch occurred.

`fetch` requires all 16 canonical official stage manifests, current final artifact hashes, seven final PT identities/iterations/configurations, ordered final frozen experts, and the already successful isolated CPU container/receipt. It imports the exact reviewed frozen monitor API read-only. It selects one independently validated export bundle per student, transfers **four ONNX files + 28 bound small JSON files**, and rejects PTs, teacher graphs, arbitrary JSON, aliases, traversal, duplicate/ambiguous bundles, stale provenance, changed bytes, and reused destinations. Before/after remote payload identities and local file SHA/size must agree. It preserves failed partial attempts and raw manifests.

Tests use synthetic files and explicit SSH/rsync/Docker doubles. They exercise the actual monitor artifact gate; they do not claim canonical final training, tensor science, ORT or simulation succeeded. The initial one-test assertion failure is retained in `initial-tests.xml`; the earlier selection-SHA gate had correctly rejected the mutation before the test's expected later ambiguity message.

Commands (host stdlib; existing SSH/rsync):

```bash
python3 -B scripts/research/pull_final_students.py status
python3 -B scripts/research/pull_final_students.py dry-run
# Only after status is ready; creates a fresh immutable cohort/initial:
python3 -B scripts/research/pull_final_students.py fetch
# After reviewing a retained failure, use a distinct fresh attempt:
python3 -B scripts/research/pull_final_students.py fetch --attempt retry-1
```

The default source is frozen tree `8d9ee8a4...`, monitor API SHA `00b7ad8d...`, cloud image `631d9e53...`. Original training bind `0093...` is untouched. Final students currently do not exist, so the real ready/fetch path and subsequent local ORT/MuJoCo remain unexecuted. `quality_verified` stays false. Exact source hashes, command, UTC and raw waiting response are in `summary.json` and `final-status-launch.json`.
