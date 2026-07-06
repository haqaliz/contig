---
name: contig-end-fast
description: Use when finishing local work on a Contig unit of work after the PR is merged and you want to clean up without generating a completion report. Triggers on "contig-end-fast", "cef", "cef bug 12", "cef feat verify-layer", "end fast".
arguments: "type id"
---

# Contig End (Fast Track)

## Overview

Closes out a unit of work's local state after the PR has merged: **master → pull → remove worktree → delete branch**, with an **optional new-version release** across every publish channel. No report (use `contig-end` / `ce` for that).

**Invocation:** `cef <type> <id>` — e.g. `cef bug 12`, `cef feat verify-layer`.

- `type` ∈ `bug | feat | feature | task | chore` (normalize `feature` → `feat`)
- `id` = the GitHub issue number, or the slug used at begin time
- Owner is `aliz`
- Branch: `<type>/<id>/aliz`; worktree dir: `.claude/worktrees/<type>-<id>`

Contig is a single repo, so this runs once.

## Pipeline

### Phase 0 — Safety check

Before removing anything:

- **Worktree clean?** `git -C <worktree> status --porcelain` must be empty. If not, stop — commit or stash first.
- **Branch merged?** Confirm the PR is merged (`gh pr view <PR> --json state,mergedAt` if reachable). `git branch -d` will refuse an unmerged branch on purpose; do not bypass with `-D` without explicit user OK.
- **You may be inside the worktree being removed.** Resolve the primary checkout first (Phase 1) and run all commands from there.

### Phase 1 — Master, pulled

Resolve the **primary** checkout (not the worktree). The first line of `git worktree list` is the primary:

```bash
PRIMARY=$(git worktree list | head -1 | awk '{print $1}')
```

Switch and pull, fast-forward only:

```bash
git -C "$PRIMARY" checkout master
git -C "$PRIMARY" pull --ff-only origin master
```

### Phase 2 — Remove worktree, delete branch

```bash
WORKTREE_NAME="<type>-<id>"   # e.g. bug-12, feat-verify-layer
BRANCH="<type>/<id>/aliz"     # e.g. bug/12/aliz, feat/verify-layer/aliz

git -C "$PRIMARY" worktree remove ".claude/worktrees/$WORKTREE_NAME"
git -C "$PRIMARY" branch -d "$BRANCH"
```

If `worktree remove` refuses due to uncommitted/untracked files, go back to Phase 0 — don't pass `--force` silently.

If `branch -d` refuses because the branch isn't merged into master, surface the message — the PR may not be merged, or there are unpushed commits. Don't use `-D` silently.

After both succeed, verify:

```bash
git -C "$PRIMARY" worktree list           # the worktree should be gone
git -C "$PRIMARY" branch --list "$BRANCH" # should print nothing
```

### Phase 3 — Release a new version (optional)

Only when this merged work should ship as a new **published** version. A release goes out across **every** channel at once: the GitHub Release binaries, PyPI, GHCR, Docker Hub, and the Homebrew tap. Most units of work do **not** release on their own (fixes batch into a later version), so ask first: *"Cut and publish a new version for this, or batch it for later?"* Default to **skipping**. If the user says skip, go straight to Phase 4.

If releasing, follow `RELEASING.md` (the source of truth) from the **primary** checkout on `master` (the merged work is already there after Phase 1).

**Release identity, do not get this wrong:** the release belongs to the **haqaliz** account, never `playdolphia`. The tag push uses the repo's git/SSH identity (haqaliz). Any manual asset upload or tap push must run with `gh` active as haqaliz (`gh auth switch --user haqaliz`). Never run `gh release create` by hand; the workflow creates the Release as `github-actions[bot]`.

1. **Pick the version.** Ask the user, or propose a semver bump from the work type: `feat` → minor, `bug`/`chore`/`task` → patch. Confirm the exact `vX.Y.Z`.
2. **Bump and changelog.** Edit `version` in `pyproject.toml` (the single `version = "..."` line under `[project]`). Then finalize `CHANGELOG.md` the Keep-a-Changelog way: insert a dated `## [X.Y.Z] - YYYY-MM-DD` header **immediately below the `## [Unreleased]` line** (leaving `[Unreleased]` in place and empty above it, so the entries already accumulated under Unreleased become this version's notes — do **not** retype them), and add a `[X.Y.Z]: https://github.com/haqaliz/contig/releases/tag/vX.Y.Z` link reference in the link block at the bottom. Commit (`chore(release): bump to vX.Y.Z (<slug>)`) and push to `master`. Wait for CI to go green before tagging.
3. **Tag and push** (this triggers `.github/workflows/release.yml`):

   ```bash
   git tag -a vX.Y.Z -m "contig X.Y.Z"
   git push origin vX.Y.Z
   ```

   The workflow builds the wheel/sdist and per-OS binaries, creates the GitHub Release, and publishes to PyPI (trusted publishing), GHCR, and Docker Hub (when the `DOCKERHUB_USERNAME` secret is set). Watch it with `gh run watch`. Each channel is an independent job, so one failing does not block the others.
4. **Homebrew tap**, once the binaries are attached to the Release: compute the three binary checksums, fill `homebrew/contig.rb` (version, the three URLs, and the sha256s), copy it to the `haqaliz/homebrew-contig` tap as `Formula/contig.rb`, and push (SSH = haqaliz). See `RELEASING.md` for the exact commands and the Rosetta fallback if the macOS Intel (`macos-13`) binary job stalls.
5. **Verify each channel is live** before calling it done: the GitHub Release page, `pip install contig==X.Y.Z` (or the PyPI JSON returning 200), `docker pull haqaliz/contig:vX.Y.Z` plus the `ghcr.io/haqaliz/contig` path, and `brew install haqaliz/contig/contig`.

Report which channels published and surface any job that failed; do not claim a channel shipped without checking it.

### Phase 4 — Comment on the issue (optional)

Optional, and only if there's a reachable GitHub issue. Ask first: *"Want me to post a short comment on the issue explaining what we did?"* If the user declines, there's nothing meaningful to say, or there's no issue (the work came from an inline brief), skip.

Otherwise:

1. **Draft a short note** (2–4 sentences). Sources, in order of preference:
   - What the user tells you to say.
   - The merged PR's title + description (`gh pr view <PR>`), if accessible.
   - A best-effort summary from the issue title and the change verb.

   Keep it friendly, light on jargon, no em dashes, no commit hashes, no file paths. The change verb matches the type: `bug → fixed`, `task → done`, `feat`/`feature → shipped`, `chore → done`. Example: *"Shipped the verification layer. Runs now self-check their outputs and flag mismatches before returning a result. Let me know if anything looks off."*

2. **Confirm the draft** with the user before posting.

3. **Post it** via `gh`:

   ```bash
   gh issue comment "$ID" --body "<confirmed comment text>"
   ```

   On success `gh` prints the comment URL. Tell the user it landed. If `gh` errors (not authenticated, Issues disabled), surface it and stop — don't retry blindly.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running from inside the worktree being removed | Resolve `PRIMARY` first, run commands from there |
| Using `git pull` (allowing merge) | Use `--ff-only` |
| Forcing branch delete with `-D` | Only after explicit user OK — `-d` refuses unmerged for a reason |
| Forcing worktree remove with `--force` | Same — never silently discard uncommitted work |
| Worktree dir vs branch confusion | Worktree dir is `<type>-<id>` (e.g. `bug-12`); branch is `<type>/<id>/aliz` |
| Posting the issue comment without confirmation | Draft first, show the user, only post after explicit OK |
| Trying to comment when the work has no issue | Skip Phase 4 — it came from an inline brief |
| Releasing every unit of work automatically | Phase 3 is opt-in; ask, default to skipping, fixes batch into a later version |
| Cutting the release as `playdolphia` | The release is haqaliz's; switch with `gh auth switch --user haqaliz`, push the tag, never `gh release create` |
| Calling a release done after pushing the tag | Watch the workflow, do the Homebrew tap, and verify every channel is live first |
