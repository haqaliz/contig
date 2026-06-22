# Phase A — Diagrams & proposal PDFs

Runs after the PRD approval gate. Everything is written inside the worktree under
`docs/planning/{slug}/`.

## 1. Diagrams (`excalidraw`)

Use the `excalidraw` skill. Decide how many diagrams the work actually needs —
don't pad. Typical set for Contig:

| Diagram | When to include |
|---|---|
| System / architecture | Almost always — where the change lives in the orchestrate→run→verify stack |
| Data flow | Data moves across steps (ingest → pipeline → artifacts → verification) |
| Sequence | A multi-step run/self-heal/verify interaction matters |
| Before / after | Behavior or structure changes visibly |
| State machine | A run/step lifecycle or failure-recovery flow changes |

Save sources to `docs/planning/{slug}/diagrams/`, descriptive names
(e.g. `architecture.excalidraw`, `verify-flow.excalidraw`).

**Every text element must set `fontFamily: 2` (Helvetica)** — the excalidraw default is hand-drawn (Virgil/Excalifont) and unreadable in stakeholder PDFs. See the excalidraw skill's Rule 5.

## 2. Export to SVG (`excalidraw-to-svg`)

Use the `excalidraw-to-svg` skill to render every `.excalidraw` to a sibling `.svg`.
Batch-export the whole `diagrams/` directory. SVG (not PNG) keeps text crisp in the PDF.

## 3. Write the two proposals

Markdown, in `docs/planning/{slug}/proposals/`. Embed the SVGs with **relative** paths
(`../diagrams/architecture.svg`) so `md-to-pdf` inlines them. Generate the two
concurrently — same PRD + diagrams, different audience.

### `<type>-<id>-technical-proposal.md` (engineers)

Filename is prefixed with the type and id (e.g. `feat-verify-layer-technical-proposal.md`) so stakeholders can identify which unit of work a proposal belongs to at a glance.

- **Summary** — one paragraph: what we're building and why.
- **Current state** — how it works today (link before/after diagram).
- **Proposed design** — architecture + components (embed architecture/data-flow/sequence SVGs).
- **Data & interface changes** — artifacts, CLI surface, run/verification contracts.
- **Risks & trade-offs** — failure modes, reproducibility impact, alternatives considered.
- **Effort & sequencing** — rough phases, dependencies.
- **Open questions** — carried from the PRD.

### `<type>-<id>-non-technical-proposal.md` (stakeholders)

Same naming convention (e.g. `feat-verify-layer-non-technical-proposal.md`).

- **The problem** — in plain language, no jargon.
- **What we'll do** — the solution at a high level (embed a simplified diagram).
- **Why it matters** — value to researchers / the business.
- **What changes for users** — visible impact.
- **Timeline** — rough, in weeks, not story points.
- **Risks** — stated honestly, in plain terms.

Keep the non-technical version free of stack names, code, and acronyms unless defined.

## 4. Convert to PDF (`md-to-pdf`)

Use the `md-to-pdf` skill. On macOS, point Puppeteer at system Chrome. Output lands
next to the input as `<name>.pdf`.

⚠️ **The proposals embed `../diagrams/*.svg`, which sits ABOVE the `proposals/` folder.**
md-to-pdf's file server is rooted at the markdown's own directory by default, so `../` paths
**silently render as broken images**. You MUST pass `--basedir ..` (the `{slug}` dir, which
contains both `proposals/` and `diagrams/`):

```bash
cd docs/planning/{slug}/proposals
PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  md-to-pdf <type>-<id>-technical-proposal.md --basedir ..
PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  md-to-pdf <type>-<id>-non-technical-proposal.md --basedir ..
```

Result: `<type>-<id>-technical-proposal.pdf` and `<type>-<id>-non-technical-proposal.pdf`.

**Verify before the approval gate (do not skip):** a missing image does NOT fail the command,
so you must *look* at the output. Render a page to an image and inspect it:

```bash
pdftoppm -png -r 70 -f 1 -l 1 <type>-<id>-technical-proposal.pdf /tmp/check   # then Read /tmp/check-1.png
```

Both PDFs must exist, be non-trivial in size, and show the diagrams (not broken-image icons).
If an image is broken, the path escaped the basedir — fix `--basedir`/filenames (URL-encode
spaces as `%20`) and re-run.

## 5. Approval gate

Present both PDFs to the user and **stop**. Only after explicit approval continue to the
`tech-plan` phase.
