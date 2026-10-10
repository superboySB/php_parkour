# Native database GUI acceptance

Passed using the original `motion_matching.play_database` in Docker motion Python and a fresh real Chrome profile with CPU SwiftShader. No native player code, frozen sim2sim dependency, GPU/DDS process, or another user's service was changed. This verifies reference database playback and GUI behavior, not policy skill success.

The player exposes 12 UI fields: 11 mutable controls and a continuously rewritten contact readout. It has no motion/variant dropdown; the database is selected by `--database`. All 11 controls were actually changed through browser clicks/keyboard events, with native loop values and browser values recorded.

- Auto Play starts advancing; pause holds the native frame; resume advances again.
- Seek selects source frames 100 and 728 with distinct actual bone rotations and native rendered pose.
- Speed 0.5 and 2.0 produced approximately 39.10 and 155.04 frames per wall-clock second during this instrumented run. These are observed rates, not a nominal playback benchmark.
- Min Frame clamps a current frame below 200 to 200; Max Frame clamps playback at 210. Native Auto Play stops at the upper bound rather than looping.
- Contact text matches the actual database contact flags. Show Contact Markers removes/restores the corresponding native scene nodes.
- Follow Character, all three camera offsets and Camera Smoothness were changed. The real connected client camera converged to root plus the selected offset within 0.02 m; look-at and up direction matched within 1e-6.

`attempt05/results.json` is the successful report; native states, logs, source and database SHA256, exact launch commands and artifact hashes are retained alongside it. Two screenshots (paused seek and followed contact pose) were visually reviewed independently by both the verifier author and the root reviewer. The original native main loop swallowed no exceptions during this run. Cleanup terminated only this attempt's verified process group; port 8081 is free afterward.

The previous four failed attempts remain immutable in `attempt01`–`attempt04`. Their reports retain the helper SHA of each attempt, logs, states and failure screenshots, but those four historical helper source versions were not archived; exact source replay is available only for successful attempt05, whose current helper is copied in `sources/`. They exposed observer/control synchronization and fixture-selection issues, documented in `summary.json`. The final verifier waits for later rendered loops, chooses source-derived distinct poses, confirms paused frame readback before seeking, and separates typed text/Enter/blur into distinct React render cycles. No native code change was needed.

Reproduce with a fresh output directory:

```bash
python3 scripts/research/verify_database_gui.py --output outputs/research/database-gui/new-attempt
```

The host uses only Python standard library and the existing Chrome executable. Project imports run in `/opt/php/bin/motion-python` inside `php-parkour-research`; `CUDA_VISIBLE_DEVICES` is empty and CPU numerical threads are limited to one.
