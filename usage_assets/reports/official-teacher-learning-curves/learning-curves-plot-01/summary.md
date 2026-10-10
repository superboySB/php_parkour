# Actual official teacher training curves

[2×2 PNG](figures/learning-curves.png) · [SVG](figures/learning-curves.svg) · [plot provenance](figures/plot-report.json) · [CPU launch/cleanup receipt](launch.json)

This is a **partial snapshot of the unfinished, running official locomotion teacher**, with **quality_verified=false** and **convergence_verified=false**. Each of the four actual TensorBoard tags contains14,341 samples, covering true iterations0–14,340. Every raw sample is plotted; the darker overlay is a trailing arithmetic mean over25 samples, using the available samples at the beginning. Negative surrogate/entropy values remain unchanged.

The original scalar export remains in `../learning-curves-snapshot-01/scalars.json`:4,171,149 bytes, SHA256 `5f165225fa2ad0bbb120783654591acefa4ae54b037be0b509219d32c33b8afd`. Its export receipt binds the official source container and TensorBoard export. Source JSON and plotting code retained their hashes during rendering.

Actual execution used the existing canonical2be185 image in one new **runc, networknone, GPU-hidden** container, Matplotlib’s Agg CPU renderer, no host scientific imports or package installation. Both Docker attach and the plotting process returned0. The exact owned CID was `757d0a1c034e4c102a781a4d38c94280f4e767aece14b9c8045e13117f142a25`; its recorded `docker stop --time10` completed and final `State.Running=false`, `State.ExitCode=0`. Other containers and training were not touched.

`executed-commands.txt` preserves the exact create/start/stop commands. Reproduction requires a fresh container name and a fresh empty figure output directory; preserve this evidence rather than overwriting it. These curves alone do not establish rollout quality or obstacle-course completion.
