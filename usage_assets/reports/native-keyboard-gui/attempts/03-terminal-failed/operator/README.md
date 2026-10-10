# Native GUI initial-settle budget repair — pending operator execution

Root's new operator command is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  outputs/research/native-keyboard-gui-runner-settle-v3/host_runner.py run \
  --plan /home/dzp/projects/php_parkour/outputs/research/native-keyboard-gui-prepared-settle-final/cohort/plan.json
```

New frozen plan: `625f7cb5d336e4b8671be961beefd92677f84e80537bd29835cd53de07f416ed`; exact canonical image remains `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`. New output directory is empty and no native operator run has been launched for this cohort. It creates only its own private display/CID under the shared host GPU lock.

Auth-v2's real attempt proved fixed hostname/FamilyLocal auth, genuine private MuJoCo window identification, foreground PTY native entries, original keyboard hold-to-move and advancing depth heartbeat. It failed before key injection because the initial1000physics-step gate used the generic12wall-second deadline. Actual41 simulator observations advanced from tick25 to1025 over13.2151346wall seconds, about75.67Hz rather than the configured500Hz target. The loop was advancing and root state was finite. Configured500Hz is a target, not achieved realtime under this visible rendering load.

Both workers were then reclaimed via actual SIGTERM (`returncode=-15`), their own groups were verified empty and the exact container stopped. This attempt remains failed and does not prove normal exit, recording or key functionality. Its untouched original manifest is `681eab055377b545fe36cb696319110b6ad5a56ceeecdffea6ca6574baf68afd`. Copies of raw text/terminal reports are in `settle-timeout-forensics/`; old attempts are never rewritten or retried in place.

This new revision changes only the helper's initial-settle wall budget to60seconds. It still requires1000actual observed physics ticks, corresponding to2simulation seconds at the configured timestep. No rate, timestep, provider, action, key, native runtime or quality gate is changed; reaching the timeout still fails. The existing300second GUI session and420second outer bound remain finite.

CPU evidence:

- `cpu-tests-settle-final/`:21/21 passed, including new999tick rejection/1000tick acceptance and explicit60second bound; also real ordinary PTY, actual Xlib exact-local/wild rejection, identity/cleanup/input/NPZ-fixture/observer parity checks.
- `cpu-imports-settle-final/`: new canonical runc/noGPU/network-none exact CLI/import/install checks again passed simulator151/inference52 modules without native objects.
- The auth implementation, fixed hostname and `private_x11_probe.py` are byte-identical to auth-v2's actual successful private Xephyr/noGPU connection/querytree proof at `../native-keyboard-gui-runner-auth-v2/private-x11-cpu-final`. Its distinct plan and source hashes remain explicit; it is not relabelled as this new native attempt.

The upcoming genuine key sequence and final receipt contract are unchanged: own MuJoCo8/9; actual XTEST→Tk terminal→TTY `]/c/=/o/i`, held-w down/up selecting1/6; two original native recorder clips (manual c save and STOP auto save), exact owned-window PNGs, original MP4 full CPU decode, original native SIGINT handlers returning actual wrappers0 and empty continuously birth-bound groups. Nonzero/130/TERM/KILL or unknown ownership fail acceptance. All source/ONNX/launch/evidence bytes are sealed. Successful completion would prove only one plane GUI interface workflow, not locomotion quality, obstacle skills or real hardware. Diagnostic I/O and visible rendering alter timing; no realtime performance is claimed.

`history-auth-v2/README.md` preserves the previous detailed interface design and authentication repair. All root/previous source data are unchanged; this directory and new plan are the only executable proposal for this next attempt.
