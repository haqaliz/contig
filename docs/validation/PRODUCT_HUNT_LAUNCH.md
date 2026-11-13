# Product Hunt launch — Contig 1.2.0

**Status 2026-11-14:** scheduled, not yet live.

| Field | Value |
|---|---|
| Product Hunt launch ID | `1315809` |
| Existing product | Contig (`1262573`) |
| Public URL (live Nov 18) | https://www.producthunt.com/posts/contig-2 |
| Maker edit URL | https://www.producthunt.com/posts/contig-2/edit |
| Launch time | **2026-11-18, 00:00 America/Los_Angeles** |
| Tagline | The local research workbench for sequencing data |
| Pricing | Free / Apache-2.0 |
| Topics | Developer Tools, Science, Artificial Intelligence, GitHub |
| Categories shown after submit | Data visualization, Medical, AI Data Scientist |

## Why Nov 18

Nov 17 was unavailable: the account already has **Pry** and **Assay**
scheduled that day, which is Product Hunt's daily launch limit. Nov 18 is the
next available Tuesday/Wednesday slot.

This is a second launch under the existing Contig product, so Product Hunt will
link it to the product and notify its followers. The launch notes the 1.2.0
research workbenches and states the validation status honestly.

## Listing

**Description**

> Contig is a local-first research workbench for sequencing data. It runs
> nf-core pipelines on your compute, self-heals common failures, verifies
> outputs with assay-aware QC, and adds variant, coverage-readiness, report,
> family, biomarker, and cohort workbenches. Every result carries citations and
> hashed provenance. Apache-2.0, no raw-read upload, research use only.

**First comment** emphasizes:

- the engine (run → self-heal → verify → reproduce);
- the 1.2.0 workbenches (variants, readiness, reports, ask, family,
  biomarkers, cohort);
- local-only execution and the local-only LLM default;
- public-data/agent validation only; design-partner validation still open;
- a 30-second smoke run and an invitation to share real failure cases.

## Media

- Thumbnail: `assets/contig-logo-240.png` (240×240). The first submit used the
  wide social card, which Product Hunt displayed as the logo; fixed 2026-11-14.
- Gallery (6): `assets/research-workbench-1270x760.png`,
  `assets/research-ask-1270x760.png`, `assets/contig-watch-1270x760.png`,
  `assets/contig-selfheal-1270x760.png`,
  `assets/contig-verify-1270x760.png`,
  `assets/contig-learn-1270x760.png` (all 1270×760).
- Video: https://youtu.be/hV_HSgJZQ5M (existing engine demo).

## Launch-day checklist (Nov 18)

1. **00:00 PT:** open the public URL, confirm it is live, and check the
   thumbnail, gallery order, first comment, and links.
2. **Respond** to every Product Hunt comment within 1–2 hours. Prioritize
   questions about install friction, bioinformatics scope, and validation.
3. **Post** the launch on the owner's channels (X/LinkedIn/Bluesky) with the
   public URL and a short “what it is / who it is for” line.
4. **Share** in nf-core Slack (`#help` or the relevant assay channel), Biostars,
   and any warm-intro threads. Ask for feedback, not votes.
5. **Send** a short note to the warm outreach contacts: “Contig 1.2.0 is on
   Product Hunt today; if it is useful, take a look and tell me what breaks.”
6. **Add** a “Featured on Product Hunt” link/badge to `site/index.html` and the
   README only after the page is live.
7. **Monitor** GitHub issues, install failures, and the smoke run; fix
   launch-day blockers immediately.
8. **Do not** claim human validation or clinical readiness. Keep the research-use
   boundary in every reply.

## Launch-day copy

**X / LinkedIn**

> Contig 1.2.0 is live on Product Hunt: a local research workbench for
> sequencing data. It runs nf-core pipelines, self-heals failures, verifies the
> output, and adds variant, readiness, report, family, biomarker, and cohort
> workbenches. Apache-2.0, local-first, research use only.
> https://www.producthunt.com/posts/contig-2

**Warm-contact note**

> Contig 1.2.0 is on Product Hunt today. It is the local research workbench for
> sequencing data — variant evidence, coverage readiness, reports, and the
> run/self-heal/verify engine. No raw reads leave the machine. If it is useful,
> take a look and tell me which defaults are wrong for your data. Research use
> only.

## Open item

The submitted listing shows the existing product categories (Data
visualization, Medical, AI Data Scientist) rather than the draft's requested
Command Line Tools / Data analysis / AI Data Scientist. Review the edit page
before launch; changing product-level categories may affect the existing Contig
product, so do not change them blindly.
