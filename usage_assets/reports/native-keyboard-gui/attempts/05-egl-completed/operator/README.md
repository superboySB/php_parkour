# Private native GUI operator — EGL offscreen diagnostic

Native terminal-v4 passed actual interface transitions and produced188/196frame recordings plus a fully decodable original MP4, but failed with simulator allocator abort after Python atexit. It remains a failed overall native GUI attempt. Its raw evidence and independent postcheck are unchanged.

This new prepared cohort changes exactly the native launch environment factor `MUJOCO_GL=glfw` to `MUJOCO_GL=egl`. Installed source shows this selects offscreen depth/video Renderer context; the visible MuJoCo passive viewer explicitly still uses GLFW. No policy/action/clock/native cleanup modification or abort suppression is included. Actual original native return0 for both workers and empty verified process groups remain mandatory.

CPU tests23/23 passed; exact native CLI parse and observer installation passed with EGL environment without constructing objects or contexts. The already-verified real private Tk/XTEST→CPU PTY routing helper is byte-identical to terminal-v4.

Only root runs the native operator, taking the shared exclusive GPU/display locks:

```bash
python3 outputs/research/native-keyboard-gui-runner-egl-v5/host_runner.py run --plan outputs/research/native-keyboard-gui-prepared-egl-final/cohort/plan.json
```

Ready means prepared and CPU-checked, not that native GUI or clean exit has passed.
