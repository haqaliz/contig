import { test, expect } from "@playwright/test";

import { FAILURE_CLASSES } from "../lib/derive";

// The dashboard's failure-class taxonomy must mirror FailureClass in
// src/contig/models.py (19 literals, same order): the pending-review relabel UI
// offers corrections from this list and the promote route validates against it,
// so a class that ships in the CLI but is missing here can neither be picked in
// the UI nor accepted by the API ("Unknown failure class." 400). This test runs
// in Node (no `page`), like the ownership-filter unit spec: it is a pure data
// pin that makes the drift greppable.

// The six literals the list used to omit. Each is reachable from real runs:
// a reference not bgzipped, a CRAM/BAM format mismatch, a missing CLI
// dependency, a full disk, a failed download, and a permissions error.
const PREVIOUSLY_MISSING = [
  "reference_not_bgzf",
  "alignment_format_mismatch",
  "missing_dependency",
  "disk_full",
  "download_failed",
  "permission_denied",
];

// The exact order of FailureClass in src/contig/models.py — the source of truth.
const PYTHON_ORDER = [
  "oom",
  "time_limit",
  "missing_reference",
  "missing_index",
  "reference_not_bgzf",
  "alignment_format_mismatch",
  "bad_param",
  "container_pull_failed",
  "container_unavailable",
  "conda_solve_failed",
  "missing_dependency",
  "platform_unsupported",
  "disk_full",
  "download_failed",
  "permission_denied",
  "tool_crash",
  "no_progress",
  "qc_anomaly",
  "unknown",
];

test("FAILURE_CLASSES lists all 19 FailureClass literals", () => {
  expect(FAILURE_CLASSES).toHaveLength(19);
});

test("FAILURE_CLASSES includes the six previously-missing literals", () => {
  for (const c of PREVIOUSLY_MISSING) {
    expect(FAILURE_CLASSES).toContain(c);
  }
});

test("FAILURE_CLASSES keeps the Python order so drift is greppable", () => {
  expect([...FAILURE_CLASSES]).toEqual(PYTHON_ORDER);
});
