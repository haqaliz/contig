---
name: contig-worktrees
description: Isolate parallel work in the Contig repo using the Claude Code worktree layout. Use when starting a new bug/feature that should not collide with another running Claude session, or when running the CLI and the dashboard from different branches at once. Covers branch naming, worktree placement under .claude/worktrees, per-worktree uv/npm setup, and cleanup.
allowed-tools: Bash, Read, Write, Edit, Glob
---

# Contig Worktree Workflow

## When to Use

- You have another Claude session running on a different branch in Contig and want to start a new bug/feature without colliding.
- You want to run two things side by side — e.g. the `contig` CLI on one branch and the `dashboard` on another.
- The primary checkout is dirty and switching branches would mix work.

Don't use this for one-off file edits that finish in a single session — a worktree is overhead for nothing if you commit + push before the next branch switch.

## Layout — the official Claude Code pattern

Contig is a **single repo**. Worktrees live **inside it** at `.claude/worktrees/<name>/`. `.claude/worktrees/` is in `.gitignore`, so worktree contents never show up as untracked files in the primary.

```
/Users/aliz/dev/at/contig/                              ← primary (master)
/Users/aliz/dev/at/contig/.claude/worktrees/bug-12/     ← bug #12 worktree
/Users/aliz/dev/at/contig/.claude/worktrees/feat-verify-layer/
```

This is the layout documented at https://code.claude.com/docs/en/worktrees. Older sibling layouts (`contig.12` next to the repo) work but make `cd` paths awkward and don't auto-trigger `.worktreeinclude` for `claude --worktree`.

## Branch naming convention

`<type>/<id>/<owner>` — owner is `aliz`. `id` is a GitHub issue number when there is one, otherwise a short descriptive slug.

- `bug/12/aliz`
- `feat/verify-layer/aliz`
- `chore/pin-nextflow/aliz`

Worktree dir name drops the slashes: `<type>-<id>` (e.g. `bug-12`, `feat-verify-layer`).

## Creating a worktree

### From master (new branch)
```bash
git fetch origin master
git worktree add -b feat/verify-layer/aliz .claude/worktrees/feat-verify-layer origin/master
```

### From an existing branch you already pushed
```bash
git worktree add .claude/worktrees/feat-verify-layer feat/verify-layer/aliz
```

### Via Claude Code's --worktree flag
```bash
claude --worktree feat-verify-layer
```
This creates `.claude/worktrees/feat-verify-layer/` on a new branch `worktree-feat-verify-layer` based on `origin/HEAD`. Your preferred ticket/slug branch names don't match that auto-generated name — when you name the work after an issue, create the branch first (as above), then `git worktree add` with the existing branch. Don't rely on `--worktree` to name it.

## Auto-copying gitignored config (`.worktreeinclude`)

A `.worktreeinclude` at the repo root lists gitignored files that should follow into new worktrees, consumed automatically by `claude --worktree`.

**Contig currently has no secrets/env files to copy** (`.gitignore` only excludes caches, `.venv/`, `/runs/`, `/_realdata/`, Nextflow state). If you later add a `.env` or similar local config, create `.worktreeinclude` and list it there, then copy manually when you use bare `git worktree add` (the include is not re-processed after creation):

```bash
# only if such files exist
cp .env .claude/worktrees/feat-verify-layer/
```

`.venv/`, `/runs/`, and `/_realdata/` are intentionally **not** copied — they are large/regenerable. Recreate the venv per worktree (below); point at shared run data by absolute path if a task needs it.

## Per-worktree setup (Python CLI — uv)

`.venv` is per-worktree and not shared:

```bash
cd .claude/worktrees/feat-verify-layer
uv sync                       # build the venv from uv.lock
uv run pytest                 # run the test suite
uv run contig --help          # the CLI entrypoint (contig.cli:app)
```

## Per-worktree setup (dashboard — Next.js / npm)

`node_modules` is per-worktree and not auto-installed:

```bash
cd .claude/worktrees/feat-verify-layer/dashboard
npm install
npm run dev                   # next dev, default port 3000
```

If the primary is already serving on 3000, override:
```bash
npm run dev -- -p 3001
```

## Switching between worktrees

```bash
git -C /Users/aliz/dev/at/contig worktree list
```

To jump into a worktree's Claude session, `cd` into the worktree dir and run `claude`. Resuming a session started in the primary on the same branch isn't supported — start a fresh session in the worktree.

## Cleaning up

After the PR merges and you no longer need the branch locally (see `contig-end-fast`):

```bash
git -C /Users/aliz/dev/at/contig worktree remove .claude/worktrees/feat-verify-layer
git -C /Users/aliz/dev/at/contig branch -d feat/verify-layer/aliz
```

`worktree remove` refuses if there are uncommitted or untracked changes. Either commit them first, or pass `--force` only if you're sure they should be discarded.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `uv run` reinstalls everything on first call in a worktree | `.venv` not shared between worktrees | Expected — `uv sync` once per worktree |
| `next dev` fails to start on 3000 | Port held by the primary's dashboard | `npm run dev -- -p 3001` or stop the other server |
| `pytest` import errors in worktree | Forgot `uv sync` (no venv yet) | `uv sync` in the worktree root first |
| `git worktree add` fails: "already checked out" | Branch is checked out in another worktree (often the primary) | `git checkout master` in the conflicting worktree, then retry |
| Worktree contents appear as untracked in primary | `.claude/worktrees/` not ignored | Confirm the `.gitignore` entry exists (it does by default) |
