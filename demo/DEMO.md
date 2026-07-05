# Contig demo: run it, watch it self-heal, get a verified, signed result

This is a scripted walkthrough of the one thing Contig does that the rest of the
market does not: it does not just generate a workflow, it RUNS the analysis on
your data and compute, debugs and self-heals the failures, and hands back a
verified, reproducible, tamper-evident result.

The whole demo takes about five minutes and runs entirely offline on a laptop —
no cloud account, no real sequencing data, and no real Nextflow run required. The
self-heal step is driven deterministically by a small generator that injects a
test executor (the same seam Contig's own test suite uses), so the failure →
recovery → PASS sequence reproduces every time you run the demo.

A note on honesty, which is the whole point of the product: everything except
that one injected executor is the real engine. The failure detector, the
diagnosis, the patch proposer, the QC verdict, the bundle writer, the Ed25519
signature, and `contig verify` are all the shipping code. The signing key used in
demo/sample-run is a throwaway key generated on the fly and then discarded; it is
NOT a real secret, and the matching public key is committed so anyone can verify
the bundle.

---

## What you will show

1. A pipeline run that hits an out-of-memory failure (exit 137) on its first
   attempt.
2. Contig detecting the OOM, diagnosing it, applying a safe resource bump, and
   re-running, with no human in the loop.
3. An honest verdict: a real PASS backed by QC checks, not a green checkmark that
   means nothing.
4. A signed, reproducible report a partner can open offline and a verification
   command that proves the result was not tampered with.

---

## Part 1: the CLI path (the core story)

### Prerequisites (one time)

From the repository root:

```bash
uv sync            # creates the venv and installs the engine and its deps
uv run contig --help
```

### Step 1: generate the guaranteed self-heal run

This drives the real self-heal loop with the injected executor and writes a
signed bundle into `demo/sample-run/`:

```bash
uv run python demo/make_sample_run.py
```

You will see:

```
Wrote signed self-heal bundle to .../demo/sample-run
  run id:  sample-run
  verdict: pass
  repairs: 1 self-heal step(s)
```

Talk track while it runs: "The first attempt failed out of memory. Contig caught
the exit 137, classified it as an OOM, bumped the memory limit on its own, and
re-ran to a clean pass. That recovery is the part nobody else does."

### Step 2: show the verdict and the repair chain

```bash
uv run contig show sample-run --runs-dir demo
```

Point at two lines in the output:

- `VERDICT: PASS`, followed by the QC checks (alignment rate and assignment rate
  per sample) that the verdict actually rests on. This is the honest-verdict
  story: Contig ran the analysis and then checked that the result is biologically
  sound, not merely that the job exited zero.
- The repair history line:
  `attempt 1: oom -> resource patch -> patched_and_retried`. This is the
  self-heal chain, captured as provenance.

To narrate the deciding checks in plain language:

```bash
uv run contig show sample-run --runs-dir demo --explain
```

### Step 3: prove it is verified and signed

```bash
uv run contig verify sample-run --runs-dir demo --json
```

Expected output:

```json
{"ok": true, "changed": [], "missing": [], "signed": true, "signature_ok": true}
```

Talk track: "`ok: true` means every recorded output still hashes to what we
captured, so the result has not drifted. `signed: true, signature_ok: true` means
the run record carries a valid Ed25519 signature, so a reviewer or a journal can
confirm nobody edited the result after the fact. The public key is right here in
the bundle."

The public key a partner verifies against is in
`demo/sample-run/PUBLIC_KEY.txt`.

### Step 4: hand over the shareable report

```bash
uv run contig show sample-run --runs-dir demo --html --output demo/sample-report.html
open demo/sample-report.html        # macOS; use xdg-open on Linux
```

This is a single self-contained HTML file (no external assets, no network) with
the verdict, the QC results, the repair timeline, and the pinned provenance. It
is already committed at `demo/sample-report.html`, so you can open it offline
without regenerating anything.

---

## Part 2: the dashboard path (the same story, with a UI)

The dashboard reads the same run bundles from disk and shells out to the same
`contig` CLI, so the run you generated above shows up in it directly.

### Step 1: start the dashboard

```bash
cd dashboard
npm install        # first time only
npm run dev        # http://localhost:3000
```

By default it reads `../runs`. To point it at the demo bundle instead, run it
with the runs directory set to the demo folder:

```bash
CONTIG_RUNS_DIR=../demo npm run dev
```

Authentication is off by default for local use, so no login is needed (see the
dashboard README Authentication section).

### Step 2: the click path

- Open `http://localhost:3000/runs`. The run list shows `sample-run` with its
  verdict pill (PASS) and a marker that self-heal kicked in.
- Click `sample-run` to open `http://localhost:3000/runs/sample-run`. Walk
  through, in order:
  - the verdict card, with the plain-language explanation and the deciding QC
    checks,
  - the output-integrity badge (verified), with its Verify action,
  - the detect to diagnose to patch to outcome repair timeline (the OOM and the
    resource bump),
  - the pinned provenance (pipeline, revision, container and input hashes), and
  - the Export and cite buttons (download the RO-Crate metadata and a
    citation-ready methods paragraph, both generated offline).

That is the whole arc on one page: it ran, it broke, it fixed itself, and the
result is verified and reproducible.

---

## Files in this demo

| File | What it is |
|---|---|
| `make_sample_run.py` | The generator: drives the real self-heal loop with an injected executor so the OOM to PASS recovery always fires |
| `sample-run/run_record.json` | The signed run bundle (the provenance record) |
| `sample-run/signature.json` | The detached Ed25519 signature over the record |
| `sample-run/PUBLIC_KEY.txt` | The public key a partner verifies against (the private key was a throwaway) |
| `sample-run/results/` | The captured outputs the record hashes, so `contig verify` checks integrity too |
| `sample-report.html` | The shareable, offline HTML report of the run |

To rebuild the bundle and report from scratch:

```bash
uv run python demo/make_sample_run.py
uv run contig show sample-run --runs-dir demo --html --output demo/sample-report.html
uv run contig verify sample-run --runs-dir demo --json
```
