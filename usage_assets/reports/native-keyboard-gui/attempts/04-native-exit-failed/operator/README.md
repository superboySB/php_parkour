# Private native GUI operator — terminal focus revision

This ignored helper is prepared for root to execute once. It does not change tracked runtime code.

The previous settle-v3 attempt is retained as a failure: actual MuJoCo 8/9 callbacks acknowledged, but XTEST `]` reached no Tk callback and no PTY bytes. A real private Xephyr/noGPU CPU probe reproduced Tk logical focus `None`. This revision binds the owned Text widget and requires its Tk logical focus before actual XTEST. Original native control semantics are unchanged.

CPU tests passed 23/23. The real private CPU probe delivered `]c=oi` as exact PTY bytes 5d/63/3d/6f/69; ordinary child SIGINT returned 0, both child groups retired empty, own noGPU container and Xephyr stopped. These CPU observations do not count as native policy GUI acceptance.

Operator command (requires exclusive GPU flock and starts real native objects):

```bash
python3 outputs/research/native-keyboard-gui-runner-terminal-v4/host_runner.py run --plan outputs/research/native-keyboard-gui-prepared-terminal-final/cohort/plan.json
```

`ready-review.json` binds exact image/plan/helpers and CPU evidence. Each original attempt and its manifest stays unchanged. The fresh cohort has no actual native output until this command is executed.
