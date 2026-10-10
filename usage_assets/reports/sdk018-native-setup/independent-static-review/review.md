# Independent static dynamic-closure review

PASS for the current selected MuJoCo + G1 Unitree + DepthDistillationPolicy source paths; native import and runtime execution remain separate gates.

Reviewed matrix SHA `5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb`. The helper produced 376 files, including 294 Python files. Independently checked 792 existing local AST import targets, 57 regular parent package initializers, 32 selected modules, 5 selected metadata entry-point targets and 34 selected robot XML asset references: none missing. See review.json for exact target/source SHA records.

- `sim2sim_scene_matrix.py:130–134` explicitly seeds Unitree bridge and inference SDK leaves selected through installed metadata.
- `sim2sim_scene_matrix.py:154–175` queues each regular parent initializer, so imports performed by parent packages are traversed recursively.
- `sim2sim.py:279–283` directly imports the depth policy. Its parent `policies/__init__.py:1–4` imports WBT and dual-mode code; all relevant local leaves are included. `wbt_utils.py:7` imports external pinocchio unconditionally, to be checked by runtime's immutable-image CPU probe.
- `utils/sim_utils.py:227–282` follows the RunSimConfig direct-simulation branch. Registered training targets that are not instantiated here do not become required solely because their strings appear in the preset menu.
- `sdk/__init__.py:9,31` and `bridge/__init__.py:9,11` resolve installed entry points. The two pyproject declarations have been recorded independently; image identity binds installed metadata, rather than the static helper itself proving metadata equivalence.

Nonblocking: bridge rglob also freezes three test Python files; no test import or execution was performed.

Static closure has explicit limits: external/native dependencies, arbitrary entry-point additions, environment-selected targets and runtime import hooks need independent import-only probes and the new isolated native pilot. This review did not create/exec a container, construct a robot, start DDS, render or use a GPU. No tracked file was edited.
