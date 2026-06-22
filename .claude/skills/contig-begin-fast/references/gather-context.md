# Gathering context with `gh` (tolerate absence)

Goal: dump the issue, its linked issues/PRs, and comments into
`docs/planning/_card/issue.md` inside the worktree. If nothing is reachable,
fall back to an inline brief from the user.

## Prerequisites

- GitHub CLI authenticated: `gh auth status`. If it errors, you're not logged in.
- Repo: `haqaliz/contig`. The current checkout's `origin` is this repo, so `gh`
  commands run from the worktree pick it up automatically.

## 0. Reachability probe

```bash
gh issue view "$ID" --json number,title >/dev/null 2>&1 && echo OK || echo FALLBACK
```

- `OK` → continue with the `gh` path below.
- `FALLBACK` (issue missing, Issues disabled, repo unresolved, or `ID` is a slug)
  → ask the user for a one-paragraph brief and write it to the dump under a
  **Brief** heading. Skip the rest of this file.

## 1. The issue itself

```bash
gh issue view "$ID" --json number,title,state,labels,author,body,url,assignees,milestone
```

`body` is Markdown already — no tag-stripping needed (unlike the old Azure HTML).

## 2. Linked / related issues and PRs

Cross-references and the timeline expose linked items:

```bash
# Comments + events, including cross-references to other issues/PRs
gh issue view "$ID" --json number,title -q .number >/dev/null
gh api "repos/haqaliz/contig/issues/$ID/timeline" \
  --jq '.[] | select(.event=="cross-referenced" or .event=="connected") | .source.issue.number' \
  2>/dev/null | sort -u
```

Fetch each referenced item (parallelize across agents when there are several):

```bash
gh issue view "$RELATED_ID" --json number,title,state,url 2>/dev/null \
  || gh pr view "$RELATED_ID" --json number,title,state,url
```

## 3. Comments

```bash
gh issue view "$ID" --comments
```

Or structured, for clean attribution:

```bash
gh api "repos/haqaliz/contig/issues/$ID/comments" \
  --jq '.[] | "[" + .user.login + " @ " + .created_at + "]\n" + .body'
```

## 4. Attachments

GitHub issue attachments are inline Markdown image/file links in the body and
comments (`![](https://github.com/.../assets/...)`). Leave images for the user
to attach separately (same convention as before). If a non-image file link is
relevant (a log, a `.txt`), download it:

```bash
curl -sSL "$URL" -o "docs/planning/_card/attachments/$NAME"   # mkdir -p first
```

## 5. Write the dump

Assemble into `docs/planning/_card/issue.md`:

- Header: number, type, title, state, author, labels, link to the issue.
- Body (verbatim Markdown).
- Linked issues/PRs: number, title, state, one-line relevance.
- Comments: chronological, attributed.
- Attachments: list of any downloaded files (note images deferred to the user).

If you took the FALLBACK path, the file is just:

```markdown
# {type} {id} — {short title}

## Brief
{the user's pasted paragraph, verbatim}
```

Either way, this file is the single source the rest of the pipeline reads from.
