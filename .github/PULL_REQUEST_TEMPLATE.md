<!-- Thanks for contributing to Contig. Keep PRs focused. See CONTRIBUTING.md. -->

## What and why

<!-- What does this change, and why? Link the issue if there is one (Closes #N). -->

## How it was tested

<!-- The tests you added or ran. Engine: `uv run pytest`. Dashboard: `npx tsc --noEmit`,
`npm run lint`, `CONTIG_AUTH_DISABLED=1 npx playwright test`. -->

## Checklist

- [ ] Written test-first: a failing test captured the behavior, then the code made it pass.
- [ ] `uv run pytest` is green (and, for dashboard changes, tsc + lint + Playwright are green).
- [ ] No em dash, en dash, or hyphen used as a pause anywhere (code, comments, docs, this PR).
- [ ] Any user input reaching the CLI or a subprocess is validated and passed safely (no shell strings).
- [ ] Stays inside the Layer-2 engine (run, debug, self-heal, verify, reproduce); not a workflow generator. If it drifts, I called it out.
- [ ] Docs updated if behavior or the surface changed (USAGE, FEATURES, ARCHITECTURE as relevant).
- [ ] No secrets committed.
