# Final-student delivery waiter: preparation only

This directory is frozen preparation for root review. No waiter daemon, SSH status, fetch, CPU native58 preparation, or native GPU job was started in this task. The only actual process test was an isolated `runc`, `--network none`, no-GPU Docker CPU test run. The readonly local `check` returned `prepared_only` with no delivery directories or waiter lock created.

Final validation: **55 passed**, `cpu-validation-transport-final/tests.xml`. The cases use synthetic ready/transfer/terminal receipts to test the control plane; these are not real final-model receipts, model-quality evidence, or execution of the future 58 cases. Actual plain CPU helper and helper→grandchild cancellation/reaping are also exercised. Earlier 43/50/53 candidates remain historical evidence, not additional independent tests to sum with 55. `candidate-50-history/wait_final_students.py` was reconstructed by reversing only the later lifecycle patch; its README states this explicitly.

Frozen waiter SHA: `049678a74ff34776120fda26da9c6ebb54c215f084929629a60fc5bfba50535f`.
Frozen tests SHA: `9d02b7194997e1b81d9c4d5413a51fc0fd8308ee27dd234f5b95cbd5a2bfd4aa`.
Contract SHA: `b4cde2ba7b361bd5f18cce9a0a10b1c234fa1519cfe5787fa14e9aef0f0d7f4f`.

## Planned sequence after explicit root launch

1. Own singleton `waiter.lock`; refuse an existing `execution` directory. Verify the contract, this waiter, workspace pull helper, native58 controls and its code-freeze receipt before/after every child action. All paths are absolute, dedicated, and reject symlinks/parent traversal.
2. Every 600 seconds call only the frozen pull helper's `status`. A waiting result writes local state/logs, and never creates the fetch/native58 cohort or probes Docker/GPU resources. Any unexpected status/transport error stops for review.
3. An actual ready receipt must pass the pull helper's strict final-16-stage/selection/CPU-ready/7-final-PT gate. Fetch exactly once into `/home/dzp/projects/php_parkour/outputs/research/final-student-transfer/waiter-delivery-01/<bound-cohort>/initial`. The helper transfers only four ONNX plus 28 JSON files. Compare ready vs actual fetch-before payload/identity, then reuse native58's local transfer verification. Changed sources, partial files, failures, and started actions are retained; no automatic retry/resume or discovery of another directory.
4. Before CPU preparation and again before native execution, require the existing fresh629 completed/zero driver and CPU exits/stopped receipt, its actual exact CID/image/StartedAt stopped state, the fixed UUID mutex available, and native58's UUID GPU-idle check. Never stop existing work. The CPU preparation itself is delegated to frozen native58; it requires actual strict fetched provenance and performs its actual no-GPU imports/config/pose/60-ORT checks.
5. Prepare the new `/home/dzp/projects/php_parkour/outputs/research/final-student-native58-delivery-01` cohort. Validate the frozen snapshot and source/origin identity. Run **the prepared cohort's `control/native58.py`**, with its explicit `--root-authorized-start`, unchanged. Native58 owns the complete GPU/container/observer lifecycle and its mutex. The waiter adds no GPU implementation or alternate native arguments.
6. Mark complete only after the actual native58 terminal receipt and four SHA-bound CPU final receipts verify 58 cases / 116 normal worker exits with empty groups / 116 exact host mappings / 58 full video decodes. `quality_verified` and obstacle-course quality remain false; real failures and thresholds are preserved.

## Root launch recommendation (not executed)

Recheck using the identical arguments with action `check` (already recorded in `preparation-receipt.json`). After independent review, the exact foreground launch is:

```bash
/usr/bin/python3 -B /home/dzp/projects/php_parkour/outputs/research/final-student-delivery-waiter-preparation/wait_final_students.py watch --contract /home/dzp/projects/php_parkour/outputs/research/final-student-delivery-waiter-preparation/contract.json --contract-sha256 b4cde2ba7b361bd5f18cce9a0a10b1c234fa1519cfe5787fa14e9aef0f0d7f4f --self-sha256 049678a74ff34776120fda26da9c6ebb54c215f084929629a60fc5bfba50535f --root-authorized-watch
```

For a detached host process root may use `nohup` with the same argv, stdin `/dev/null`, dedicated stdout/stderr files inside this directory, and record PID/starttime/argv/source and contract SHAs. Do not start it in Docker or an environment that changes the fixed host paths. No new package installation is needed.

## Cancellation, failure and limits

The waiter is a dedicated single-thread Linux stdlib process. Each own helper enters a new session; PID/PGID/SID/start ticks are saved before signals are unblocked. SIGTERM becomes controlled cancellation. For `status`/`fetch`, cancellation checks the own leader identity, sends only that private transport session SIGINT, and allows a 30-second grace. A transport which ignores SIGINT may remain; its cleanup error and remaining members are retained and the waiter fails for **manual review**, without escalation/KILL, another fetch, or a new native start. Therefore total reclamation is not promised.

For `prepare`/`run`, cancellation checks the own Popen identity and sends only native58's Python helper SIGINT; it waits for native58's own finally cleanup and adds no external timeout/KILL. SIGKILL/host crash cannot be handled. An existing execution directory is never resumed automatically, including one left while waiting; root must inspect retained state and owned resources before authorizing a distinct reviewed cohort. Root should use SIGTERM instead of SIGKILL.

Current final-model readiness was **not queried online in this preparation**. The actual daemon will observe it after root starts it. No claim is made that final models, selective transfer, 60 final-model ORT cases, or the final 58 native cases have already passed. Active official training, posttrain watch, fresh629, production sources, and main documentation were not modified.
