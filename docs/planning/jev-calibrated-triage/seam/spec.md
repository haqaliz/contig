# Spec — Aspect: `seam`

Slice of the PRD: the injectable `Triage` seam, `NullTriage` default, `JevTriage`
implementation, the whitelisted egress payload builder, and the Contig-owned JSON
transport contract. Jev's API is unverified from the repo; everything CI-observable
in this aspect is ours.

## In-scope (PRD R1, R2-seam-half, R6, R7)

- `src/contig/triage.py`: `Triage` Callable type alias (returns a Contig-owned
  `TriageResult`), `NullTriage`, `default_jev_triage`, the payload builder
  (`build_triage_payload`), the defensive response parser (`parse_triage_response`),
  and a single `_urlopen` patch point.
- `CONTIG_JEV_KEY` gate: absent/empty ⇒ `NullTriage`, no network, no error
  (the `extract_with_llm` degrade pattern, NOT the raising `get_detector` one).
- `CONTIG_JEV_URL`: https-only (non-https refused by the seam; `http://localhost`
  allowed for the manual live gate behind an explicit documented env opt-out).
- Whitelisted numeric QC metrics/metadata payload (`build_triage_payload`); one
  whitelist declaration; item ids `{run_id}:{surface}:{check}`.
- Response: `{"items": [{"id", "confidence"}]}`, defensive parse, malformed ⇒ Null
  behavior; 30 s timeout; size-bounded response; stdlib only (urllib/json).

## Out-of-scope

CLI flags, self_heal/verify wrap sites, heal-scenario threading, the ledger sidecar
and `contig triage-stats` (aspects `wiring`, `ledger`); any vendor SDK; any verdict
authority; any active-mode skipping (wiring aspect).

## Acceptance (test-first, no network in CI)

1. `NullTriage` returns the "no triage" result without touching env/network.
2. Key absent ⇒ `default_jev_triage` behaves as Null and no request is constructed
   (asserted on the constructed-request seam), exit unchanged.
3. Payload whitelist: mutation control — a raw-read field (fastq/bam/vcf path or
   bytes, sample identifier beyond the opaque id) can never appear in a constructed
   payload.
4. Non-https URL refused by the seam; `https://` accepted; `http://localhost`
   accepted only with the documented opt-out.
5. Malformed/oversized/timeout response ⇒ Null behavior, never raises.
6. Confidence values outside [0, 1] rejected (defensive).
7. Real `default_jev_triage` transport asserted for URL/JSON shape only, never
   executed; a `manual`-marked live test exists (S2) and skips by default.

## Dependencies & sequencing

First aspect (nothing depends on it). Sequenced within: payload builder →
NullTriage → JevTriage transport → whitelist mutation control. No `models.py`
change; no new dependency (`pyproject.toml`/`uv.lock` untouched).

## Open questions / risks

- Exact Jev endpoint shape unverified — the seam intentionally makes the http
  round-trip the only uncompiled surface; the manual live gate validates it.
- Payload field list: derive from real `QCResult` fields at build time; keep the
  builder signature `build_triage_payload(run_meta, checks)` so wiring can feed it
  without reaching into records.