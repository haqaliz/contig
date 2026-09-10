# Card: feat/reference-known-sites-capture/aliz

**Source:** inline brief (no GitHub issue — `id` is a slug). Tracker probe:
`gh issue list` shows one open issue, #33 (flaky reproduce freshness guard),
unrelated to this work.

**Owner:** aliz · **Branch:** `feat/reference-known-sites-capture/aliz`

---

## Brief

Capture known-sites (dbsnp / known_indels) into C5's `ReferenceIdentity` provenance,
the next slice of the least-complete capability. The reference-identity capture slice
already pins FASTA/GTF sha256 and renders it in `contig methods` + the provenance
panel; this pins the second data class the run used.

**Caveat:** sarek's known-sites are nf-core config assets, not CLI params Contig sees
today, so start the dig by designing the `--known-sites` surface (where the user's
files come from, how they reach `params`, and how capture degrades to checksum `None`
rather than a fabricated hash, per the C5 capture slice's own rule).

**Scope intent (confirm during interview):** capture-only — no verdict/exit-code
change, test-first, render in `contig methods` + HTML, round-trip through
`rerun`/`resume` like `ReferenceIdentity` does.

**Out of scope (blocker-deferred siblings):** the GTF-version resolution slice (no
reliable source) and the assembly-signature pre-flight mismatch form (no sample-side
contig signal) must NOT be scoped in.

## Source grounding

- `docs/technical/CAPABILITY_ROADMAP.md` C5 (`:1183-1200`): capture slice shipped;
  deferral list names known-sites capture as the next C5 slice ("needs a
  `--known-sites` design").
- `docs/technical/CAPABILITY_ROADMAP.md:1199`: GTF version "no reliable source — left
  null, not fabricated" (blocker-deferred, out of scope).
- `CHANGELOG.md:452`: assembly-signature pre-flight form "no sample-side contig
  signal" (blocker-deferred, out of scope).
- `FEATURES.md:254`: C5 row still lists known-sites as pending.

## Guardrail check

Layer 2 (run / self-heal / verify / reproduce) — reference-integrity provenance on
the reproduce layer. No Layer 1, no wet-lab/clinical dependency, no raw-read egress.