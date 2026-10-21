# Wrap-up: where Contig stands at v0.64.0

**Released 2026-10-21.** `v0.64.0` closes 34 of the 87 items in the engine
capability backlog. The other 53 are **not open work in the ordinary sense** —
each one names what it waits on. This file is the closing summary; `BACKLOG.md`
is the row-level ledger and `BLOCKED_RUNBOOK.md` is the evidence list.

## Shipped in v0.64.0

- **Verification honesty:** a missing MultiQC report is UNVERIFIED, not absent;
  the never-firing `rrna_contamination` slug is gone; a non-UTF-8 `results.json`
  degrades instead of crashing; non-UTF-8 and vanished-coverage paths pinned.
- **Self-heal:** `--auto-approve` cannot apply a destructive patch; the choice
  gate is advisory-honest; the container wait is recorded; BAM `.csi` uses
  samtools; the observed peak rides the corpus; `platform_unsupported` is now
  guarded (25 scenarios, outcome-match 1.0, 18 covered classes).
- **Somatic assay:** PON/germline-resource wiring (replayed on rerun/resume),
  tumor-vs-normal VAF delta, Strelka2-native normal VAF.
- **Reference integrity:** known-sites contigs are checked against the reference
  at pre-flight; a different assembly refuses before launch.
- **Reproduce:** private-repo tokens, submodules, direct PDF URLs,
  `--pdf-extractor`, notebook tag addressing, named regex flags, 32 MiB notebook
  bound, regex/numeric table predicates, checkout pruning, and a real loopback
  test of the DOI fetcher.
- **Eval/dashboard:** repair-stats history + card, verify-guard trend, reproduce
  summary, stall evidence, triage ledger, C1 corroboration line, C3 plausibility
  cards, somatic swap card.

Guard trend points recorded for the release: eval-guard 93.3% (14/15),
heal-guard 100% (25/25, 18 classes), verify-guard 95.5% (21/22),
reproduce-guard 94.1% (16/17). Each has one deliberate known miss.

## What is left, and what each group waits on

| Group | Count | Waits on |
|---|---|---|
| Todo | 8 | Design work, not follow-ons (see below) |
| Blocked | 20 | Real runs, real cohorts, or an upstream artifact the repo does not have |
| Needs-decision | 15 | A policy call only the owner can make |
| Gated | 6 | The roadmap's own revisit triggers (live trigger, experiment, on-by-default evidence) |
| Declined | 4 | Hard-blocked by the stdlib-only contract or explicitly out of scope |

### The 8 todo items

`C1-5` (single-cell STAR index auto-build), `C3-4` (multi-sample support),
`C5-1` (assembly-signature mismatch — likely blocked: no sample-side signal),
`C5-3` (GTF version resolution — likely blocked: no reliable source),
`C8-20` (PDF-table extraction — needs a real corpus), `C8-24` (version pinning
from a trace — needs a trace contract), `C8-25` (venv isolation — environment
model), `C9-2` (a fifth eval guard — no agreed axis). None is a small follow-on;
each is a design session.

### The 15 decisions

The recurring ones, with the honest trade:

1. **`C2-5`** — should the reference-recompress patch auto-apply (`safe`)? It
   only writes a scratch copy, but it widens unattended action.
2. **`C2-6`** — `--fasta`-only for sarek is refused today; add a per-pipeline
   reference contract or keep the coupling.
3. **`C8-8`, `C8-12`, `C8-17`, `C8-18`** — four additive facts that would change
   the signed `ReproduceRecord`/`ClaimResult` payload. They belong in one
   deliberate signature-break release, not four silent ones.
4. **`C9-1`, `C9-2`, `C2-9`, `C2-11`, `C2-22`** — all need an axis or a market
   that does not exist yet; the roadmap records "no precedent to reuse".
5. **`C1-1`, `C1-2`, `C3-2`, `C7-2`** — dependency-gated or large new
   capabilities (`.h5ad`, clustering, doublets, variant prioritization).

### Blocked, by category

- **Real-run gates (5):** C2-23 Nextflow/Batch smoke, C7-3 VEP/SnpEff smoke,
  C8-26 real-repo smoke, C8-27 bare-commit fetch policy, C8-28 live-LLM seam.
- **Band calibration (8):** C1-3, C2-8, C2-13, C3-7, C3-8, C4-2, C6-3, C9-4.
- **Missing upstream artifact/data (7):** C3-1, C3-3, C3-6, C3-9, C3-10, C2-20,
  C7-1.

`BLOCKED_RUNBOOK.md` says exactly what to collect for each and what to change
once you have it.

## How to resume

Pick the first `todo` row in `BACKLOG.md`, or unblock a category by doing its
runbook entry. The discipline that got here stays: test-first, one commit per
item, full suite green, guards unmoved unless refrozen deliberately.

## What not to do

Do not "finish" the declined or gated rows by inventing a source: the C3-11
removal in this release exists precisely because a guessed slug sat in the pack
for months looking like coverage.
