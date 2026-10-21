# Contig — wrap-up backlog (all remaining capability items)

**Status 2026-10-21 (wrap-up pass 2):** 34 done / 8 todo / 20 blocked / 15
needs-decision / 6 gated / 4 declined. Done items are on `master`; see
`CHANGELOG.md`. Remaining "todo" rows are the only ones that are both
buildable and unblocked; every other row names what it waits on.

Source of truth: `docs/technical/CAPABILITY_ROADMAP.md` (latest status resolved, 2026-10-21).
Status legend: `todo` · `planning` · `in-progress` · `done` · `blocked` (needs real hardware/data/network) · `declined` (by design, not work).

Workflow per item: `contig-begin-fast` → worktree `.claude/worktrees/<type>-<id>`
→ PRD `docs/planning/{slug}/prd.md` → plan → TDD implementation → suite green.

| ID | Capability | Item | Type | Status |
|----|-----------|------|------|--------|
| C1-1 | C1 | `.h5ad`/AnnData second-matrix parsing (dependency-gated) | code | needs-decision |
| C1-2 | C1 | Cell-count + cluster-stability agreement across quantifiers | code | needs-decision |
| C1-3 | C1 | FAIL severity on calibrated concordance bands | calibration | blocked |
| C1-4 | C1 | Dashboard "corroborated by" line | code | done |
| C1-5 | C1 | Single-cell STAR `--index` auto-build at verify time | code | todo |
| C1-6 | C1 | Explicit `contig verify` somatic concordance flag/echo | code | done |
| C2-1 | C2 | Classic BWA index build/redirect | code | gated (no live trigger) |
| C2-2 | C2 | bwa-mem2 build/redirect (detector shipped) | code | gated (no live trigger) |
| C2-3 | C2 | Classic-vs-mem2 aligner-mismatch heal | code | gated (no live trigger) |
| C2-4 | C2 | CRAM↔BAM conversion repair (revisit trigger) | code | gated (no live trigger) |
| C2-5 | C2 | `safe`-vs-gated auto-approval for reference-recompress patch | code | needs-decision |
| C2-6 | C2 | `resolve_reference` `--fasta`/`--gtf` coupling quirk | code | needs-decision |
| C2-7 | C2 | Fold observed peak into `FailureCase` corpus schema | code | done |
| C2-8 | C2 | Stall-window calibration on real runs | calibration | blocked |
| C2-9 | C2 | Stall-specific escalation (widen / give up after 2) | code | needs-decision |
| C2-10 | C2 | Stall dashboard surface | code | done |
| C2-11 | C2 | Per-task stall detection | code | needs-decision |
| C2-12 | C2 | Stall watchdog on-by-default (decision-gated) | code | gated (roadmap: revisit trigger is real-run evidence) |
| C2-13 | C2 | Walltime factor/ceiling calibration on real data | calibration | blocked |
| C2-14 | C2 | `repair-stats --snapshot/--history` trend | code | done |
| C2-15 | C2 | `repair-stats` dashboard card | code | done |
| C2-16 | C2 | `risk="destructive"` no-op to engine; no `--auto-approve` carve-out | code | done |
| C2-17 | C2 | `_write_pending_choice` advisory branch (unreachable today) | code | done |
| C2-18 | C2 | `container_unavailable` wait leaves no trace in `RepairStep.detail` | code | done |
| C2-19 | C2 | Still-missing single-file index kind (BAM/CRAM `.csi`) | code | done |
| C2-20 | C2 | Exhaustive per-assembly alias-table completeness | code | blocked (needs upstream data/artifact) |
| C2-21 | C2 | Runtime `reference_mismatch` detector-corpus case | code | done |
| C2-22 | C2 | Pin conflict repair (container/dependency repin) | code | needs-decision |
| C2-23 | C2 | Real Nextflow/Batch run smoke (incl. `-resume` of SIGKILLed task) | manual | blocked |
| C3-1 | C3 | Gene-body-coverage evenness (needs RSeQC compute path) | code | blocked (needs upstream data/artifact) |
| C3-2 | C3 | Doublet rate (single-cell; needs scanpy/scDblFinder) | code | needs-decision |
| C3-3 | C3 | Coverage-from-VCF | code | blocked (needs upstream data/artifact) |
| C3-4 | C3 | Multi-sample / per-sample support | code | todo |
| C3-5 | C3 | Dashboard cards for C3 packs | code | done |
| C3-6 | C3 | Reported-vs-inferred sex concordance | code | blocked (needs upstream data/artifact) |
| C3-7 | C3 | Capture-type-aware (WGS/WES/panel) bands + calibration | calibration | blocked |
| C3-8 | C3 | Sex-check FAIL severity on calibrated bands | calibration | blocked |
| C3-9 | C3 | Structured QCatch-JSON recognizer for simpleaf path | code | blocked (needs upstream data/artifact) |
| C3-10 | C3 | Mitochondrial-fraction plausibility | code | blocked (needs upstream data/artifact) |
| C3-11 | C3 | `rrna_contamination` guessed `percent_rRNA` slug | code | done |
| C3-12 | C3 | MultiQC `None` gate: checks vanish instead of UNVERIFIED | code | done |
| C4-1 | C4 | Panel-of-normals / germline-resource reference wiring | code | done |
| C4-2 | C4 | `normal_median_vaf` FAIL severity + band calibration | calibration | blocked |
| C4-3 | C4 | Directional tumor-vs-normal ratio/delta metric | code | done |
| C4-4 | C4 | Strelka2-native normal VAF | code | done |
| C4-5 | C4 | Dashboard "corroborated by" surface for swap signal | code | done |
| C5-1 | C5 | Assembly-signature form of pre-flight reference mismatch | code | todo |
| C5-2 | C5 | Known-sites / GTF-version consistency checks | code | done |
| C5-3 | C5 | Annotation/GTF version resolution | code | todo |
| C6-1 | C6 | `platform_unsupported` heal-guard coverage (needs `AttemptSpec.exit`) | code | done |
| C6-2 | C6 | Verify-guard dashboard trend card | code | done |
| C6-3 | C6 | Real-run labeling into verify + reproduce corpora | calibration | blocked |
| C7-1 | C7 | Annotation-pack FAIL severity | code | blocked (needs upstream data/artifact) |
| C7-2 | C7 | Research-use variant prioritization | code | needs-decision |
| C7-3 | C7 | Real VEP/SnpEff/sarek post-merge smoke (GRCh37 iGenomes) | manual | blocked |
| C8-1 | C8 | Regex/numeric row predicates + column ranges | code | done |
| C8-2 | C8 | Figure/plot & table-cell(-image) claims (no plot-hash, stdlib-only) | code | declined (hard-blocked by the stdlib-only contract) |
| C8-3 | C8 | `contig reproduce <doi>` DOI resolution | code | declined (roadmap says out of scope in 3 places) |
| C8-4 | C8 | Dashboard card(s) for reproduce | code | done |
| C8-5 | C8 | `occurrence: first\|last` + `group` override | code | gated (roadmap: gated on a counted experiment over 5 real repos) |
| C8-6 | C8 | `flags` array for patterns | code | done |
| C8-7 | C8 | Regex over binary files | code | declined (decoding binaries to regex is a footgun, no user need) |
| C8-8 | C8 | Persist matched output on the record | code | needs-decision |
| C8-9 | C8 | Notebook-specific size bound | code | done |
| C8-10 | C8 | `metadata.tags` / multi-key / regex cell matching | code | done |
| C8-11 | C8 | Non-text notebook outputs | code | declined (no numeric value to bind) |
| C8-12 | C8 | Structured staleness field on `ClaimResult` | code | needs-decision |
| C8-13 | C8 | Non-UTF-8 `results.json` raises `UnicodeDecodeError` | code | done |
| C8-14 | C8 | Private-repo credentials | code | done |
| C8-15 | C8 | Submodules | code | done |
| C8-16 | C8 | Checkout pruning | code | done |
| C8-17 | C8 | Hash bundle's post-run `source/` copy | code | needs-decision |
| C8-18 | C8 | Local `source_commit` / dirty-state capture | code | needs-decision |
| C8-19 | C8 | Direct non-doi.org PDF URLs | code | done |
| C8-20 | C8 | PDF-table extraction | code | todo |
| C8-21 | C8 | `--pdf-extractor` override | code | done |
| C8-22 | C8 | Loopback-server test of the real urllib DOI path | code | done |
| C8-23 | C8 | `pattern`/notebook locator inference (exactly-one blocker) | code | needs-decision |
| C8-24 | C8 | Version pinning from a traced execution | code | todo |
| C8-25 | C8 | venv isolation | code | todo |
| C8-26 | C8 | Real-repo reproduce smoke test | manual | blocked |
| C8-27 | C8 | Fetch-by-bare-commit server policy | manual | blocked |
| C8-28 | C8 | Live-LLM `extract_with_llm` seam | manual | blocked |
| C9-1 | C9 | Self-heal attempt ordering (no axis exists) | code | needs-decision |
| C9-2 | C9 | A fifth C6 guard | code | todo |
| C9-3 | C9 | Jev dashboard surface | code | done |
| C9-4 | C9 | Jev budget calibration from ledger data | calibration | blocked |

**Totals:** 87 items — 74 code, 13 blocked (5 manual gates + 8 calibration).
Explicitly declined by design (not work): 16 items listed in the roadmap's
"declined/settled" notes (RNA-seq + somatic FAIL bands, `pon_applied` band,
`eval-guard` deliberate miss, BGZF fix target, BAM→CRAM, wrong-reference
masquerade, full-clone fallback, AWS Batch undiagnosability, `_applied_word`
alignment, `--step annotate`, `gene_symbol_concordance` severity, default exit code).

Blocked items: see `BLOCKED_RUNBOOK.md` for the evidence each one needs.

Execution order: dependency-first (C3-12, C8-13, C2-16 correctness fixes), then
C5 → C2 → C3 → C4 → C1 → C8 → C6 → C7 → C9.
