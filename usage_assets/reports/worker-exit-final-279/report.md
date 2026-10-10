# Final stopped-cohort text audit supplement

The old driver is terminal with exit 1. Selection records retain 279 completed, 5 execution_failed, 1 running and 344 planned; no complete-coverage claim is valid. The stale top-level completed count is 2. The halt receipt records no live native process.

The last four completed cases (high_speed_climb_58 configs 24–27) add eight SHA-matching sealed worker logs. None contains the requested fatal/traceback strings. Carried forward with the preserved 275-case report, 10 of 279 parent-zero completed cases have explicit simulator SIGSEGV logs. Absence of a fatal line does not prove a worker-zero exit.

Three additional failures are retained below. All have parent exit 1 and body JSON reporting 500 inference ticks and completed simulation. No role log has a fatal/traceback match. A kernel command_writer fault is time-correlated shortly after inference JSON; historic host-TID to worker-PID mapping is unavailable.

| Case | Ready simulator / inference PID | Inference JSON UTC | Kernel fault UTC | Parent error mtime UTC | Simulation JSON UTC | Parent exit UTC | Height/tilt threshold |
|---|---|---|---|---|---|---|---|
| low_speed_climb_58:0031:right_45_walk2.0s_plat1.2s | 65298 / 65367 | 2026-10-10T07:35:57.577733+00:00 | 2026-10-10T07:35:57.635837+00:00 | 2026-10-10T07:35:57.994806+00:00 | 2026-10-10T07:35:58.565094+00:00 | 2026-10-10T07:35:59.417315+00:00 | False |
| high_speed_climb_58:0000:run_forward_0.6s_step0.1s | 67029 / 67062 | 2026-10-10T07:38:55.163134+00:00 | 2026-10-10T07:38:55.219838+00:00 | 2026-10-10T07:38:55.536232+00:00 | 2026-10-10T07:38:56.469180+00:00 | 2026-10-10T07:38:57.309007+00:00 | True |
| high_speed_climb_58:0023:run_left_90_1.5s_step1.0s | 71265 / 71298 | 2026-10-10T07:46:30.769544+00:00 | 2026-10-10T07:46:30.826837+00:00 | 2026-10-10T07:46:31.159139+00:00 | 2026-10-10T07:46:31.577277+00:00 | 2026-10-10T07:46:32.430808+00:00 | False |

For each failure the inference body report precedes the kernel fault, then the parent records an error, then the simulator saves its body JSON, and finally the parent exits 1. A body report is not interpreter-shutdown completion. Low/high climb58 fall outside the five released training bundles; do not turn this process-failure audit into skill-completion claims.

`sdk-pilot-failed-case-identities.json` lists all five original failure identities for future explicitly planned tests; it does not represent new execution. `report.json` gives exact original bytes/SHA, sealed-log comparisons, kernel messages, clocks, and limits. `evidence-manifest.json` hashes the retained text snapshots.

- Only new four completed cases and three additional execution_failed cases were reread; previous 275/old17/old12 findings are carried forward by original report SHA.
- Media were neither read, hashed, decoded nor copied; only JSON/log/CSV/text and zero-byte stop markers were retained. Source NPZ/NPY/OBJ and 340 frozen dependencies were not rescanned.
- A parent-zero/artifact-sealed old attempt is not proof that its workers returned zero. Even a log without a fatal string cannot establish worker return codes.
- Kernel timestamps correlate with cases; without historical host/container thread mapping or native backtrace, do not treat temporal correlation as exact PID attribution or definitive SDK causality.
- Simulation height/tilt events are a separate quality heuristic, not an explanation for process shutdown failures and not obstacle-course completion.
- Stopped matrix deliberately retains running/planned labels and stale top-level counts; selection counts plus halt/terminal wrapper receipts describe its actual incomplete state.
