# Native GUI terminal-v4 independent postcheck

Overall failed: simulator native Python 57 aborted after original main returned and Python atexit was observed. The Kit shell retained `free(): invalid next size (fast)` / `Aborted (core dumped)` and returned 1. Inference returned 0. Both process groups became empty with verified birth ownership, and the exact container and private Xephyr stopped. These cleanup observations do not turn the native abort into success.

Actual interface scope passed before failure: MuJoCo 8/9, real terminal `]`, `c`, `=`, `o`, `i`, XTEST held/released `w` with command1/6 and return0, manual save and STOP autosave. Independent Docker CPU checks found 188 and196 frames, finite float32 qpos(36)/command(15), one-hot command1=152 frames and command6=158 frames, fps50, normalized wxyz and rootXYZ placeholder zero. They are native inference recordings, not motion-training bundles. The one original MP4 decoded fully without errors; all original manifest entries were checked.

Installed primary sources confirm `MUJOCO_GL=egl` changes offscreen Renderer GLContext only, while `viewer.py` explicitly initializes GLFW for the visible passive viewer. A fresh one-factor EGL cohort is a reasonable diagnostic, not a proven fix. The original native viewer destructor only clears a reference and does not explicitly call Handle.close; no close shim, os._exit, signal normalization or abort suppression was added.

The figures and recordings prove interfaces and observable robot state only. They do not prove obstacle traversal, realtime performance, training convergence, DDS motor delivery acknowledgement or real hardware operation.
