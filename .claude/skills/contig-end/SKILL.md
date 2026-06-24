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

**REQUIRED SUB-SKILL:** Use `contig-end-fast` for the cleanup and release pipeline.

Run its **Phase 0 → Phase 3 exactly as written** (safety check → master + pull → remove worktree → delete branch, then the **optional** new-version release across every publish channel). The release in its Phase 3 is opt-in: ask, and default to skipping. Only proceed to the report once cleanup verification passes.

### Phase 4 — Completion report

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

### Phase 5 — Comment on the issue (optional)

Same approach as `contig-end-fast` Phase 4 — ask the user, draft (using the issue + the just-generated report as source material), confirm, then `gh issue comment <id>`. Skip if there's no reachable issue.

The comment can mirror the report's plain-English summary in a sentence or two. Same tone rules: no em dashes, no jargon, no commit hashes. Skip entirely if the user declines.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running the report before cleanup | Phases 0–2 first; the report is last |
| Skipping the report on purpose | Use `contig-end-fast` / `cef` instead |
| Passing the wrong type to `contig-report` | Apply the mapping table (`feat`/`feature` → `feature`, `chore` → `task`) |
| Posting the issue comment before the report | The comment (Phase 5) comes after the report (Phase 4); the report's plain-English summary is good source material |
| Auto-releasing during end | The release is `contig-end-fast` Phase 3 and is opt-in; ask, default to skipping, and it belongs to haqaliz not playdolphia |
| Posting the comment without confirmation | Draft first, confirm with the user, then post |
