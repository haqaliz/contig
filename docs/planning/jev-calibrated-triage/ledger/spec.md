# Spec — Aspect: `ledger`

Slice of the PRD: the unsigned `runs/triage-ledger.jsonl` calibration sidecar, the
read-only `contig triage-stats` command, the egress/whitelist documentation, and the
CAPABILITY_ROADMAP C9 re-baseline onto master (the branch text is 76 commits stale).

## In-scope (PRD R8, S1, docs)

- Ledger row shape (Contig-owned dataclass or plain dict): run_id, attempt,
  surface (`qc_anomaly` | `verify_concordance`), mode (`shadow` | `active`), the
  whitelisted payload inputs, Jev confidence (or `null` when the seam was Null), and
  the actual outcome — which checks ran and their recorded statuses, or
  UNVERIFIED-when-skipped. **Note: the append helper (`append_ledger_row`) ships in
  the `wiring` aspect** (wiring owns the call sites); this aspect consumes it.
- `contig triage-stats` (repair-stats precedent, `cli.py:4286`): reads the sidecar
  `<runs_dir>/triage-ledger.jsonl` (precedent: `pending_verify_corpus.jsonl`,
  `cli.py:2345`; unsigned by construction) across runs; reports row counts by
  surface and mode, confidence-vs-actual cross-tab where outcomes exist (mean
  confidence of shadow rows whose checks later ran vs skipped), and an honest note
  when the ledger is absent/empty or nothing is yet measurable. `--json` flag for
  the dashboard, mirroring repair-stats.
- Docs: whitelist + egress contract written into `triage.py` docstring and one
  ARCHITECTURE-adjacent note; CAPABILITY_ROADMAP C9 section re-baselined onto the
  current master file (label C9 "slice 1 shipped" per this work, carry the honest
  limits and the revisit trigger verbatim).
- Revisit trigger support: the PRD's trigger counts "ledger rows and skip events"
  via this command, no new instrumentation (R8-conformant).

## Out-of-scope

A fifth C6 guard; a dashboard card; any calibration math beyond the cross-tab
(no reliability curve/ECE in slice 1 — recorded as C6 fold-in successor); purse
changes to run/verify exit codes.

## Acceptance (test-first)

1. Append: one row per triaged decision; absent key ⇒ zero rows and no file.
2. Rows round-trip: `triage-stats` parses a written ledger and counts it; a
   malformed line is tolerated (skip + count, snapshot_history tolerance precedent)
   and never raises.
3. `contig triage-stats` on an empty/absent ledger exits 0 with an honest
   "nothing yet measurable" message — never a false confidence claim.
4. `--json` output shape is stable and keys match repair-stats conventions.
5. Unwritable ledger path degrades silently (ledger append never fails a run or
   verify).

## Dependencies & sequencing

Third aspect (after `wiring`). No `models.py` change; no new dependency.

## Open questions / risks

- Cross-tab granularity: confidence is per-decision, outcome is per-check-status —
  the report must not over-claim a "calibration curve" from zero/one real keyed
  runs; state the row counts the table is built on.
- Re-baselining C9 into the roadmap is a docs change this repo ships per-feature;
  keep the diff minimal (add the C9 section + sequencing-table row + shipped
  markers) so review is cheap.