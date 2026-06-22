---
name: contig-end
description: Use when finishing local work on a Contig unit of work after the PR is merged and you also need a completion report on Desktop. Triggers on "contig-end", "ce", "ce bug 12", "ce feat verify-layer", "end full".
arguments: "type id"
---

# Contig End (Full Track)

## Overview

Same cleanup as `contig-end-fast`, **plus** a completion report at the end via `contig-report`.

**Invocation:** `ce <type> <id>` — e.g. `ce bug 12`, `ce feat verify-layer`.
Arguments and conventions are identical to `contig-end-fast`.

## Pipeline

**REQUIRED SUB-SKILL:** Use `contig-end-fast` for the cleanup pipeline.

Run its **Phase 0 → Phase 2 exactly as written** (safety check → master + pull → remove worktree → delete branch). Only proceed to Phase 3 once cleanup verification passes.

### Phase 3 — Completion report

**REQUIRED SUB-SKILL:** Use `contig-report` with the unit-of-work id and the corresponding type.

The two skills use slightly different type vocabularies — map before invoking:

| `ce` arg | `contig-report` arg |
|---|---|
| `bug` | `bug` |
| `task` | `task` |
| `chore` | `task` |
| `feat` | `feature` |
| `feature` | `feature` |

Example: `ce bug 12` → invoke `contig-report` with `bug` + `12` → writes `/Users/aliz/Desktop/bug-12-completion.md`.

`contig-report` fetches the issue via `gh` when reachable (otherwise works from the merged PR / what we just did) and produces the standard template. If it asks for a screenshot/video, provide one (or hand it to the user to attach), then confirm the file landed on Desktop.

### Phase 4 — Comment on the issue (optional)

Same approach as `contig-end-fast` Phase 3 — ask the user, draft (using the issue + the just-generated report as source material), confirm, then `gh issue comment <id>`. Skip if there's no reachable issue.

The comment can mirror the report's plain-English summary in a sentence or two. Same tone rules: no em dashes, no jargon, no commit hashes. Skip entirely if the user declines.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running the report before cleanup | Phases 0–2 first; the report is last |
| Skipping the report on purpose | Use `contig-end-fast` / `cef` instead |
| Passing the wrong type to `contig-report` | Apply the mapping table (`feat`/`feature` → `feature`, `chore` → `task`) |
| Posting the issue comment before the report | Phase 4 comes after Phase 3; the report's plain-English summary is good source material |
| Posting the comment without confirmation | Draft first, confirm with the user, then post |
