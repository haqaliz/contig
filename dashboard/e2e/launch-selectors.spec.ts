import { test, expect } from "@playwright/test";

// Backend and engine selectors on the launch form (PRD contract F). The form lets
// a user choose where the run executes (local or SLURM, with a partition and an
// account when SLURM) and which engine runs it (nextflow or snakemake). Local and
// nextflow are the defaults, so the common path is unchanged. We assert the
// selectors render with their defaults and that picking SLURM reveals the
// partition and account inputs. We deliberately do NOT launch: a launch needs
// fixture data and a previewed plan, and would spawn a real run; the dispatch argv
// wiring is validated in the engine and lib/runs suites.

test("the launch form shows backend and engine selectors with defaults", async ({
  page,
}) => {
  await page.goto("/runs/new");

  const backend = page.getByRole("combobox", { name: "Backend" });
  const engine = page.getByRole("combobox", { name: "Engine" });
  await expect(backend).toBeVisible();
  await expect(engine).toBeVisible();
  // Local + nextflow are the defaults, so the common path stays unchanged.
  await expect(backend).toContainText("Local");
  await expect(engine).toContainText("Nextflow");

  // The SLURM-only fields are hidden until SLURM is selected. (Account is scoped to
  // the textbox role: the header user menu also carries an "Account" label.)
  await expect(page.getByRole("textbox", { name: "Partition" })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Account" })).toHaveCount(0);
});

test("choosing the SLURM backend reveals the partition and account inputs", async ({
  page,
}) => {
  await page.goto("/runs/new");

  await page.getByRole("combobox", { name: "Backend" }).click();
  await page.getByRole("option", { name: "SLURM" }).click();
  await expect(
    page.getByRole("combobox", { name: "Backend" }),
  ).toContainText("SLURM");

  // SLURM needs a partition (the queue); an account is offered too. Account is
  // scoped to the textbox role: the header user menu also carries an "Account" label.
  await expect(page.getByRole("textbox", { name: "Partition" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Account" })).toBeVisible();
});

test("choosing the Snakemake engine keeps the backend on local", async ({
  page,
}) => {
  await page.goto("/runs/new");

  await page.getByRole("combobox", { name: "Engine" }).click();
  await page.getByRole("option", { name: "Snakemake" }).click();
  await expect(
    page.getByRole("combobox", { name: "Engine" }),
  ).toContainText("Snakemake");

  // The engine choice is independent of the backend; local stays the default, so
  // no SLURM fields appear.
  await expect(
    page.getByRole("combobox", { name: "Backend" }),
  ).toContainText("Local");
  await expect(page.getByRole("textbox", { name: "Partition" })).toHaveCount(0);
});
