# Fresh629 publisher compatibility review

The current `scripts/research/publish_full_scene_matrix.py` **cannot directly publish this isolated fresh629 cohort**. Its strict rejection is safe; the current run is still in progress and is not certified by this audit.

Six concrete boundaries need a separate strict cohort adapter:

1. Legacy `host_path` maps `/outputs` to the wrong directory, `/workspace` to live source, and does not map `/data/matrix.json`. The actual mounts are `base/{outputs,source,inputs,control}`.
2. Legacy driver/launch keys and direct-driver argv differ from the actual fresh host schema1 receipt and `/control/run_frozen_matrix.py` invocation. Validate the original host receipt, do not fabricate old-schema success JSON.
3. Correct path translation alone still fails the shared validator's `ROOT` anchor. A read-only probe confirmed the live imported validator rejects it; the unchanged frozen cohort matrix module accepts the first real completed case's three receipts.
4. Require/recheck all1258 exact hostwriter PID/TID birth/namespace mappings and original observer/CID/image/birth receipts. The current publisher checks only native receipts.
5. Bind the actual terminal CPU full-validation report:629 full MP4 decodes,1258 workers, exact case/result/receipt/video SHA+bytes. Current publisher only checks stored metadata and PNG dimensions.
6. Bind/recheck the host plan and all5206 frozen files, CPU preflight and wrapper identities. Current publisher verifies native376+1887+models+matrix closure only.5206 is a total frozen-file count, not distinct motion inputs.

The existing byte-copy/history/threshold-preservation/paged-gallery logic can be reused after those gates. Original JSON, namespace paths, failed attempts and quality=false remain unchanged. No GPU/native/daemon/SSH/Docker, publishing, decoding, tests or tracked/raw edits occurred. See [review.json](review.json) for exact source hashes, line references, actual read-only probes and minimum adapter tests.
