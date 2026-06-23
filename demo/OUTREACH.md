# Outreach and the design-partner session guide

The goal of Phase 0 is not adoption and not revenue. It is one decision: do real
bioinformaticians reach for a credit card after using Contig on their own data.
The Phase 0 to Phase 1 gate is explicit in docs/ROADMAP.md: PROCEED if at least 3
of 5 design partners reach for a credit card (give a card, sign a paid pilot, or
give an unambiguous "yes, I or my lab would pay $X from a named budget"); PIVOT if
fewer than 3. Everything below serves that one question.

---

## Cold outreach message

Keep it short, specific, and about their pain, not our product. One ask: 30
minutes, them watching, on their data.

Subject: 30 min: watch a tool fix a broken RNA-seq run by itself

Hi [name],

I am building a tool for the part of analysis nobody enjoys: not writing the
workflow, but getting it to actually run, debugging the failures, and trusting
the result. It runs the pipeline on your data and your compute, self-heals the
common failures (out of memory, a missing index, a malformed sample sheet, a
reference mismatch), and hands back a verified, reproducible, signed result.

I am not selling anything. I am looking for 5 people who run RNA-seq (or wrangle
variant calling) and have felt that pain, to spend 30 minutes letting me watch
them try it on one of their own analyses. I want to learn where it helps and
where it falls down.

Could I grab 30 minutes with you in the next two weeks? If it is easier to see
first, I can send a two minute recording of it catching a run that runs out of
memory and recovering on its own.

Thanks,
[you]

Variations worth keeping ready:

- For a core-facility lead: lead with reproducibility and a signed, citable
  record per run, the thing they get asked to defend.
- For a wet-lab scientist who cannot code: lead with "you describe the analysis,
  it runs it and tells you honestly whether the result is sound", and drop the
  failure-mode jargon.

---

## Design-partner session guide

A session is 30 to 45 minutes, them driving, you mostly silent. The point is to
observe a real analysis, not to give a polished demo. Run the scripted demo
(DEMO.md) only if they ask to see it work first.

### Before the session

- Confirm they bring one real analysis: a sample sheet, the FASTQ locations, and
  a reference they actually use. Real data is the whole point; a toy run proves
  nothing about willingness to pay.
- Have the local dashboard ready (`cd dashboard && npm run dev`) and the CLI
  working, so a launch is one form or one command.

### During the session: what to watch

- Where do they hesitate. The first place they get stuck is your most important
  finding, more than anything they say.
- Do they trust the verdict. When Contig says PASS or FAIL, do they believe it,
  or do they go re-check by hand. Trust in the verdict is the product.
- The self-heal moment. When a failure recovers on its own, do they lean in, or
  shrug. Their reaction here is the signal for the core IP.
- Reproducibility and the signature. Do they care that the result is signed and
  re-runnable. For some ICPs this is the whole value; for others it is noise.
  Note which.
- What they ask for next. The first feature they request tells you what they
  think they are buying.

### Do not

- Do not coach them through a failure. Let it fail and watch whether Contig, and
  then they, recover. A coached success is a false positive.
- Do not pitch. Answer questions, then go quiet.

### The money question (run it with all five)

Ask it plainly at the end, every time, and record the exact answer:

"If this ran your analyses end to end and self-healed the common failures, is this
something you (or your lab) would pay for? If yes, what would you pay, and out of
whose budget?"

### What counts as a yes

A yes is a credit card, a signed paid pilot, or an unambiguous "yes, I or my lab
would pay $X from [named budget]". Anything softer ("this is cool", "I would
totally use a free version", "maybe if it also did X") is a no for the gate, and a
useful one: write down why, because the reason is the next experiment. Do not add
features and hope.

### After each session

Capture, per user: the analysis they brought, where they got stuck, whether they
trusted the verdict, their reaction to the self-heal, the exact WTP answer, and
the first feature they asked for. Five of these notes are the Phase 0 decision.
