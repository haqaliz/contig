---
name: contig-report
description: Use when a Contig unit of work (bug, task, feature) is done and you want a brief, friendly, non-technical completion note saved on Desktop to share with the team.
allowed-tools: Read, Grep, Glob, Bash, Write
arguments: "type id"
---

# Contig Completion Note

A short, friendly, non-technical heads-up that a unit of work is done. Written like a teammate would write it — no jargon, no commit hashes, no checklists. Just one plain-English sentence about what changed, plus a link and a screenshot.

## Arguments

- `type` ∈ `bug | task | feature`
- `id` = the GitHub issue number, or the slug used at begin time

Usage: `/contig-report bug 12` or `/contig-report feature verify-layer`.

## When to use

- A unit of work is finished and you want to let the team know in a human way.
- You've closed (or are about to close) a GitHub issue, or merged its PR.

## Output

Markdown file saved to `/Users/aliz/Desktop/{type}-{id}-completion.md`.

Examples:
- `/Users/aliz/Desktop/bug-12-completion.md`
- `/Users/aliz/Desktop/task-pin-nextflow-completion.md`
- `/Users/aliz/Desktop/feature-verify-layer-completion.md`

## The template

One template, three small verb tweaks. Keep it warm, short, and free of technical detail.

```markdown
## #{id} - {Feature or area} - {Short Title}

Hey! Quick note that this one's {verb}.

**What changed (in plain words):**
{One or two friendly sentences. What's different for the user now. No jargon. No em dashes.}

**See it live:** {link to the PR, the dashboard area, or the CLI command}
**Screenshot/video:** {attached, or link}

If anything looks off or you'd like a tweak, just say the word.
```

Verb per type:

| Type | Verb |
|---|---|
| `bug` | fixed |
| `task` | done |
| `feature` | shipped |

## Tone rules

- Write like you're messaging a teammate, not filing a ticket.
- Plain English only. Swap out words like *deduplicated, refactored, idempotent, artifact, schema, pipeline DAG, contig, orchestrator* for everyday phrasing.
- No checklists, no testing matrices, no commit hashes, no branch names, no file paths — those live in the PR, not in this note.
- Two or three short paragraphs max. If it reads like docs, trim again.
- **Never use the em dash character `—` in the note.** It's a tell that an AI wrote it. Use a comma, a period, or a regular hyphen with spaces (`-`) instead.
- A friendly closer is welcome ("Let me know what you think.", "Happy to revisit if needed.").

## Workflow

1. **Get the context.** Prefer the GitHub issue if reachable; otherwise use the merged PR or what we just did:
   ```bash
   gh issue view "$ID" 2>/dev/null || gh pr view "$PR" 2>/dev/null
   ```
   If neither resolves, write the note from the work you just completed in this session.
2. **Distill** the change into one or two plain sentences. Resist the urge to add detail.
3. **Pick the "See it live" target** that fits the work: the merged PR link, the dashboard page (e.g. `http://localhost:3000/...` or the deployed URL), or the exact CLI command a teammate would run (`uv run contig ...`).
4. **Ask the user for a screenshot or short video** if one isn't already on hand.
5. **Write** the note to `/Users/aliz/Desktop/{type}-{id}-completion.md` and tell the user it's ready.

## Optional: cross-check

Only include if the user explicitly asks for it. Append one short, friendly line:

```markdown
**Also checked:** {a couple of related areas you peeked at, in plain words}
```

Don't add this by default — it makes the note look like an audit.

## Example (feature)

```markdown
## #34 - Verification - Output self-check

Hey! Quick note that this one's shipped.

**What changed (in plain words):**
Runs now double-check their own results before handing them back, so if something looks off it gets flagged instead of slipping through.

**See it live:** run `uv run contig run sample.fastq` and watch the verify step at the end
**Screenshot/video:** attached

If anything looks off or you'd like a tweak, just say the word.
```
