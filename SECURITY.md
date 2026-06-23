# Security Policy

Contig runs real pipelines on a user's own data and compute, shells out to a CLI,
and (in the dashboard) gates access with Auth0, so we take security seriously.

## Reporting a vulnerability

Please do NOT open a public issue for a security vulnerability. Instead, report it
privately:

- Use GitHub's "Report a vulnerability" (Security tab, private advisory) on this
  repository, or
- email the maintainer (see the address on the GitHub profile of the repository
  owner).

Include what you found, how to reproduce it, and the impact you see. We will
acknowledge the report, work with you on a fix, and credit you if you would like.
Please give us a reasonable window to release a fix before any public disclosure.

## Scope and design notes

A few properties the project relies on, useful when assessing a report:

- Genomic data and intermediates stay in the user's `work_dir`; the control plane
  and provenance record file names, checksums, QC metrics, and logs, never sequence
  content.
- User input that reaches the CLI or a subprocess is validated (charset, no leading
  dash) and passed as `--opt=value` with a `--` terminator before positionals; the
  engine never builds a shell string from user input.
- Self-heal patches are typed operations, not free-text shell; a risky patch pauses
  for human approval.
- Secrets (Auth0 client secret, signing key, SMTP, LLM keys) come only from
  environment variables, are never logged, and must never be committed.
- The dashboard is auth-gated (Auth0) with per-user and per-workspace run isolation;
  the documented `CONTIG_AUTH_DISABLED` bypass is for local and CI use only and must
  not be enabled on an exposed instance.

If you find a case where any of the above does not hold, that is exactly the kind of
report we want.
