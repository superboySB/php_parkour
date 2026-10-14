This directory contains prepared source only. No candidate source was imported or executed, and no browser, Docker, SSH, package installer, model or simulation was launched during preparation. AST parsing and byte hashes admit source, not a passed browser result.

The borrowed `viser_browser.py` is an exact copy of `usage_assets/reports/reference629-full-browser/sources/viser_browser.py`; only its standard-library CDP and free_port definitions are imported at runtime. Its original main is never invoked. The verifier pins its complete SHA256 before importing it and disables bytecode writes.

Run after the genuine package exists, with an existing Chrome/Chromium:

```bash
python3 -B outputs/research/official-full/official-evaluations-six-browser-preparation-02/verify_gallery.py \
  --package usage_assets/reports/official-evaluations-six \
  --output outputs/research/official-full/official-evaluations-six-browser-01
```

`--output` must not already exist or overlap the package. The verifier visits local `playback.html` in a new temporary Chrome profile with `--headless=new`, `--disable-gpu`, `--disable-background-networking`, and recorded complete argv. It does not serve HTTP, install packages, or use Docker. Only its own browser is closed; it requests Browser.close and records the real Popen.wait result, with bounded SIGTERM/SIGKILL fallback for the owned process group if necessary. Success requires the natural wait returning strict integer0; fallback shutdown is reported honestly and does not yield passed. stdout/stderr remain raw files.

The package schema is agreed with root: summary.json `stages` in the six contract labels/order, each `{label, representative:{path,bytes,sha256,duration_seconds,width,height,probed_frames,decoded_frames}, ...}`. playback.html has exactly six `article[data-label]` elements, each containing a video with the representative relative `src` and `poster="cpu-02/results/LABEL/representative.png"`. The verifier binds DOM values to the actual summary, checks original video SHA/bytes and positive equal CPU frame counts, browser metadata/dimensions, six midpoint seek completions, all six PNG browser decodes/dimensions, and actual playback advancement for all six videos. It captures the full document as playback.png. No additional claim about all160 browser decodes is made; those full media decodes belong to the separate genuine CPU02 audit.

`report.json` records each measurement, exact source/input before/after snapshots, browser argv/PID, cleanup method, actual browser wait returncode and status. quality_verified/full remain false. A failed metadata, image, seek, play, source/input mutation or normal-exit check yields failed and process exit1. Success yields process exit0. This preparation contains no fabricated runtime report or screenshot. The verifier is approximately12KB to keep all six measurement checks, file binding and actual process cleanup explicit; the borrowed helper remains unchanged.

Independent static source review found the exact borrowed helper can busy-loop when its HTTP handshake receives EOF before the header terminator. The verifier preserves the helper bytes and bounds only its constructor with a15-second SIGALRM, closing the partially allocated socket on failure and restoring the prior handler/timer. This guard was source-reviewed and AST-parsed only; it has not been executed.
