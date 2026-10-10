# GUI auth repair — new cohort, pending native operator execution

The first real attempt is preserved at `../native-keyboard-gui-prepared-final`. It failed before simulator/inference worker spawn: Tk/libX11 connected, but python-xlib0.33 ignored the FamilyWild auth record and sent no credential. Worker receipts are empty; the exact owned container stopped and Xephyr group was verified empty. `first-attempt-forensics/` copies terminal raw reports and binds the untouched original manifest.

The minimal repair gives the new Docker container an explicit unique `--hostname php-gui-<token>` and writes two exact FamilyLocal authority records for host and container, sharing only the new private server's unlogged random cookie. No xhost access rule, authentication bypass or host authority change is used. A new connection-only probe now precedes all native workers. Host receipts distinguish GUI driver launch from actual native worker entry.

Root's new operator command (after reviewing this directory and confirming no shared-lock owner) is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  outputs/research/native-keyboard-gui-runner-auth-v2/host_runner.py run \
  --plan /home/dzp/projects/php_parkour/outputs/research/native-keyboard-gui-prepared-auth-final/cohort/plan.json
```

Fixed plan SHA: `33bc6b9fca939987e8ee2a3d5faa8a7cdc8040407823893ecc2de4a47f727638`. Exact image: `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`. Exact GPU: `GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25`. All 3298 actual canonical-context files are copied, with 3310 files after the documented entry observers/helpers. Both actual wrappers and native original entry copies retain canonical bytes. The full snapshot and local released ONNX pair are SHA/byte-bound to this new plan. Its output directory is empty; no native operator run has been launched for this new cohort.

Completed CPU verification:

- `cpu-tests-auth-final/tests.xml`: 20/20 passed. Includes exact FamilyLocal positive and wrong-host/FamilyWild negative matching against the actual python-xlib matcher, real ordinary stdlib PTY, original observer call/return parity, changed-birth no signal, nonzero preservation, partial-start log-error cleanup registration, private-display/XID/client guards, input hashes and host/native mapping tests. Synthetic NPZ fixtures do not prove actual recording.
- `cpu-imports-auth-final/`: canonical runc/noGPU/network-none imports, exact native CLI parsing and diagnostic-wrapper installation passed again for simulator151/inference52 source modules. No Robot/SDK/policy/sim/viewer/listener was constructed.
- `private-x11-cpu-final/report.json`: **actual** new isolated Xephyr plus exact fresh runc/noGPU/network-none Docker connection-only test passed. Python-Xlib authenticated, verified root token/XTEST/RECORD and queried the root tree. No keys, Tk window, native object or GPU compute request. Exact CPU container stopped; own Xephyr birth group is retired/empty/verified. All raw logs and SHA manifest are retained; the ephemeral cookie is removed and excluded.

The real operator run still requires genuine private XTEST→Tk-terminal→foreground-PTY `]/c/=/o/i` and held-w down/up, MuJoCo8/9 callbacks, native low/high command acknowledgements, c-manual-save and o-STOP-autosave original NPZs, actual owned-window PNGs, native MP4 CPU full decode and both original KeyboardInterrupt handlers returning actual wrapper0 with empty descendant groups. Two seconds of initial simulation settle and three advancing original heartbeat polls are observed. No extra heartbeat poll, state refresh, action/provider/key mapping or SDK implementation is substituted. Diagnostic I/O changes timing, so this is not a performance benchmark.

`DirectSimulation.run` is `while True`, so closing a passive viewer cannot be relied on to stop the sim. Exact birth-verified native Python SIGINT follows original handlers; Esc is not policy stop. Nonzero/130/TERM/KILL or unknown/leaked descendant groups fail native acceptance. Cleanup only targets the exact labelled new CID and continuously birth-verified own process groups. Input is restricted to token-bearing private display and owned XIDs. The host GPU flock covers the entire operator attempt and rejects concurrent work immediately.

The original broad design remains in `history-original-proposal/README.md`; its old plan, FamilyWild method and old command are historical only. This repaired directory and fixed new plan supersede them. Native acceptance and locomotion/course quality remain unverified until the root operator run finishes; this interface test will not claim hardware deployment or obstacle skill success.
