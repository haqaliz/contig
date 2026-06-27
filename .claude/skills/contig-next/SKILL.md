---
name: contig-next
description: Use when deciding what to build next in Contig and you want the single highest-leverage feature picked from the repo's own roadmap and planning files (not invented), grounded in the moat and in what has already shipped or been deferred, ending with a ready-to-run handoff. Triggers on "contig-next", "cn", "what's next", "next feature", "pick next".
arguments: ""
---

# Contig Next (pick the most important feature)

## Overview

Read the repo's own roadmap and planning files, rank the real candidate features
against the moat and against what has shipped or been deferred, and recommend the
single highest-leverage one to build next. End with a ready-to-paste
`contig-begin-fast` invocation so the next session can start that worktree.

This skill RECOMMENDS and hands off. It does NOT create a worktree or start
`contig-begin-fast` itself; the user runs the handoff prompt when ready.

## When to use

- "what should I build next", "pick the next feature", at the start of a session.
- After a release or a merged feature, when choosing the next unit of work.
- Not for: executing a chosen feature (use `contig-begin-fast`), or planning an
  already-chosen one (use `prd-interview` / `tech-plan`).

## The candidate set is the FILES, never invented

Read these (the source of truth, in this order). If a `graphify-out/` graph
exists, you may query it, but the planning docs are authoritative for intent:

- `docs/technical/CAPABILITY_ROADMAP.md`: the C1..C6 engine capabilities and their
  SHIPPED / pending markers, with per-capability deferrals.
- `FEATURES.md`: the dashboard roadmap and the engine-capability table.
- `docs/ROADMAP.md`: the phased plan and the gates between phases.
- `docs/technical/USE_CASE_UNIVERSE.md`: the broader assay backlog AND the clinical
  bright line (what is out of scope by design).
- `CHANGELOG.md` and `git tag`: what actually shipped, by version. Trust this over
  prose; code is often ahead of the narrative docs.
- `docs/planning/*/`: in-flight, completed, and DEFERRED work. Read the
  `understanding.md` notes: a feature deferred for a real blocker (for example
  "no metric source") must not be re-recommended as if it were a quick win.
- `CLAUDE.md`: the moat and the guardrails the pick must obey.

## How to rank (grounded in CLAUDE.md)

1. **Layer 2 only.** Run / self-heal / verify / reproduce. Never Layer 1 (NL to
   workflow). Never anything needing wet-lab or clinical credentials, proprietary
   datasets, or regulatory integration. Drop any candidate that violates this.
2. **Deepen the moat and capture eval data.** Favor work that hardens
   verify/self-heal/reproduce and that gets better as base models improve.
3. **Respect shipped and deferred state.** Do not re-recommend something the
   CHANGELOG or a SHIPPED marker says is done, nor something deferred for a real
   blocker (name the blocker if you mention it).
4. **Unblocked and depth-first beats broad and shallow.** Prefer a candidate with a
   clear, testable slice over one with an unresolved feasibility question.
5. **Demand-pull beats push for new assays.** A new assay is stronger when a design
   partner asked for it than when the roadmap merely lists it.
6. **Follow-on slices count.** A shipped capability's next slice (for example making
   a manual feature turnkey) is a valid, often high-leverage candidate.

## Process

1. Read the files above. Build the candidate list: pending capabilities, follow-on
   slices of shipped ones, and any demand-pulled assay. For thoroughness on a large
   tree, you may dispatch one read-only agent to summarize the planning docs.
2. For each candidate, record: shipped-state (cite the file), moat-leverage, the
   nearest dependency or feasibility risk, and any known blocker from the docs.
3. Rank by the rules above. Pick ONE, plus one or two alternates.
4. Sanity-check the pick against the guardrails (Layer 2, founder's edge, not
   deferred-for-a-blocker).
5. Produce the handoff (below).

## Output format

- **The pick**: one line naming the feature and a kebab-case slug.
- **Why**: 2 to 3 bullets tying it to the moat and to what shipped, each citing a
  file.
- **Alternates**: one or two lines.
- **Known caveat**: the nearest feasibility risk, stated honestly, so the
  `contig-begin-fast` dig is not surprised by it.
- **Handoff prompt** (ready to paste): a `cbf feat <slug>` line plus a 3 to 5
  sentence inline brief that includes the caveat. Make clear the user runs this to
  start the worktree; this skill does not start it.

## Honesty rules

- Ground every shipped / pending / deferred claim in a named file. Do not assert
  from memory; the CHANGELOG and tags win.
- If the strongest-looking candidate has a real blocker, say so and rank it
  accordingly rather than papering over it.
- Recommend only features the files support. If the files are thin, say the pick is
  based on discussion, not an artifact.

## Common mistakes

| Mistake | Fix |
|---|---|
| Inventing a feature not in the docs | The candidate set is the files; cite where each came from |
| Re-recommending shipped work | Check CHANGELOG and the SHIPPED markers first |
| Re-recommending blocker-deferred work | Read the `docs/planning` deferral note; name the blocker |
| Recommending Layer 1 or clinical work | Drop it against the CLAUDE.md guardrails |
| Starting the worktree from this skill | Only recommend and hand off; the user runs `cbf` |
| A vague pick with no slice | Prefer a candidate with a clear, testable first slice |
