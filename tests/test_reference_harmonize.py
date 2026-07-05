"""Tests for reference_harmonize: pure decision + GTF stream-rewriter.

Real files only, via pytest tmp_path; no mocks, no network.
Covers the decide-and-rewrite slice of the self-heal reference-mismatch feature.
"""

import gzip
from pathlib import Path

import pytest

from contig.reference_check import check_reference_consistency
from contig.reference_harmonize import HarmonizationPlan, harmonize_gtf, plan_harmonization


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def _write_gz(path: Path, text: str) -> Path:
    with gzip.open(path, "wt") as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------------------
# Helpers for building minimal valid FASTA / GTF content
# ---------------------------------------------------------------------------

def _fasta(*contigs: str) -> str:
    return "".join(f">{c}\nACGT\n" for c in contigs)


def _gtf_row(seqname: str) -> str:
    return f'{seqname}\tsource\tgene\t1\t100\t.\t+\t.\tgene_id "g1"\n'


def _gtf(*seqnames: str) -> str:
    return "".join(_gtf_row(s) for s in seqnames)


# ===========================================================================
# Part 1 — plan_harmonization
# ===========================================================================


class TestPlanHarmonization:

    # --- direction == "add_chr" -------------------------------------------

    def test_chr_fasta_bare_gtf_returns_add_chr(self, tmp_path):
        """chr-prefixed FASTA + bare disjoint GTF → plan with direction add_chr."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.direction == "add_chr"

    def test_add_chr_plan_has_samples(self, tmp_path):
        """Plan carries non-empty fasta_sample and gtf_sample strings."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.fasta_sample  # non-empty
        assert plan.gtf_sample

    # --- direction == "strip_chr" -----------------------------------------

    def test_bare_fasta_chr_gtf_returns_strip_chr(self, tmp_path):
        """bare FASTA + chr-prefixed disjoint GTF → plan with direction strip_chr."""
        fa = _write(tmp_path / "ref.fa", _fasta("1", "2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "chr2"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.direction == "strip_chr"

    # --- consistent inputs → None ----------------------------------------

    def test_full_overlap_returns_none(self, tmp_path):
        """Shared contigs on both sides (full overlap) → None."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "chr2"))
        assert plan_harmonization(fa, gtf) is None

    def test_strict_subset_gtf_returns_none(self, tmp_path):
        """GTF is a strict subset of FASTA (no mismatch) → None."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2", "chrX"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "chr2"))
        assert plan_harmonization(fa, gtf) is None

    # --- not a chr asymmetry → None --------------------------------------

    def test_both_bare_disjoint_returns_none(self, tmp_path):
        """Both bare naming schemes but genuinely different assemblies → None."""
        fa = _write(tmp_path / "ref.fa", _fasta("1", "2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("X", "Y"))
        assert plan_harmonization(fa, gtf) is None

    # --- post-transform still disjoint → None ----------------------------

    def test_chr_asymmetric_but_transform_still_disjoint_returns_none(self, tmp_path):
        """FASTA {chrA,chrB} vs GTF {1,2}: add_chr gives {chr1,chr2}, no overlap → None."""
        fa = _write(tmp_path / "ref.fa", _fasta("chrA", "chrB"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        assert plan_harmonization(fa, gtf) is None

    # --- empty / unparseable → None --------------------------------------

    def test_empty_fasta_returns_none(self, tmp_path):
        """Empty FASTA → None (uncomparable)."""
        fa = _write(tmp_path / "ref.fa", "")
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        assert plan_harmonization(fa, gtf) is None

    def test_empty_gtf_returns_none(self, tmp_path):
        """GTF with only comments → None (uncomparable)."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1"))
        gtf = _write(tmp_path / "genes.gtf", "# only a comment\n")
        assert plan_harmonization(fa, gtf) is None

    def test_unparseable_both_returns_none(self, tmp_path):
        """Files with no parseable contigs → None."""
        fa = _write(tmp_path / "ref.fa", "no header here\n")
        gtf = _write(tmp_path / "genes.gtf", "#all\n#comments\n")
        assert plan_harmonization(fa, gtf) is None

    # --- determinism -------------------------------------------------------

    def test_identical_inputs_produce_identical_plan(self, tmp_path):
        """Same files called twice → byte-identical plan."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        plan1 = plan_harmonization(fa, gtf)
        plan2 = plan_harmonization(fa, gtf)
        assert plan1 == plan2

    def test_plan_is_frozen_dataclass(self, tmp_path):
        """HarmonizationPlan is a frozen dataclass (immutable)."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        with pytest.raises((AttributeError, TypeError)):
            plan.direction = "strip_chr"  # type: ignore[misc]

    # --- alias-aware rename map (Phase 2) -----------------------------------

    def test_ucsc_ensembl_full_alias_and_prefix_mix(self, tmp_path):
        """FASTA UCSC {chr1,chr2,chrM} vs GTF Ensembl {1,2,MT}: mixed
        prefix + mito-alias renames; direction is 'alias' since not every
        rename follows a single uniform pattern."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2", "chrM"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2", "MT"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.rename_map == {"1": "chr1", "2": "chr2", "MT": "chrM"}
        assert plan.direction == "alias"
        assert plan.unmatched == ()

    def test_residual_mito_only_rename(self, tmp_path):
        """Autosomes already match; only the mitochondrion needs renaming."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2", "chrM"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "chr2", "MT"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.rename_map == {"MT": "chrM"}

    def test_pure_alias_both_chr_prefixed(self, tmp_path):
        """Both sides chr-prefixed but mito spelled differently: chrMT -> chrM."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chrM"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "chrMT"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.rename_map == {"chrMT": "chrM"}

    def test_hybrid_fasta_lookup_wins(self, tmp_path):
        """FASTA itself uses the hybrid spelling chrMT: GTF bare MT resolves
        against the actual FASTA set, not a fixed convention."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chrMT"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "MT"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.rename_map == {"MT": "chrMT"}

    def test_pure_prefix_add_still_labeled_add_chr(self, tmp_path):
        """Uniform add_chr rename set keeps the legacy 'add_chr' label."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.rename_map == {"1": "chr1", "2": "chr2"}
        assert plan.direction == "add_chr"

    def test_pure_prefix_strip_still_labeled_strip_chr(self, tmp_path):
        """Uniform strip_chr rename set keeps the legacy 'strip_chr' label."""
        fa = _write(tmp_path / "ref.fa", _fasta("1", "2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "chr2"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.direction == "strip_chr"

    def test_unmatched_contig_enumerated_rest_still_harmonized(self, tmp_path):
        """A contig with no FASTA candidate lands in unmatched; the rest of
        the GTF is still harmonized."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2", "chrM"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2", "MT", "weirdcontig"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.unmatched == ("weirdcontig",)
        assert plan.rename_map == {"1": "chr1", "2": "chr2", "MT": "chrM"}

    def test_wrong_assembly_no_candidates_refuses(self, tmp_path):
        """No GTF contig has any FASTA candidate at all → refuse (None)."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("scaffold_1", "scaffold_2"))
        assert plan_harmonization(fa, gtf) is None

    # --- injectivity guard (refuse-on-ambiguity, no silent contig merge) ---

    def test_colliding_targets_refuse(self, tmp_path):
        """FASTA {chrM,chr1} + GTF {M,MT}: both M and MT resolve to the same
        FASTA target chrM. Applying that rename map would silently merge two
        distinct GTF seqnames onto one contig, so plan_harmonization must
        refuse rather than hand back an ambiguous map."""
        fa = _write(tmp_path / "ref.fa", _fasta("chrM", "chr1"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("M", "MT"))
        assert plan_harmonization(fa, gtf) is None

    def test_renamed_collides_with_staying_contig_refuses(self, tmp_path):
        """FASTA {chr1} + GTF {1,chr1}: renaming '1' -> 'chr1' collides with
        the GTF's own already-matching 'chr1' seqname. Two distinct source
        seqnames would land on the same target → refuse."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "chr1"))
        assert plan_harmonization(fa, gtf) is None

    def test_distinct_targets_still_harmonize(self, tmp_path):
        """Positive control: a normal UCSC/Ensembl mix where every renamed
        target is distinct must still produce a valid plan (the injectivity
        guard must not over-refuse ordinary harmonizable input)."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2", "chrM"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2", "MT"))
        plan = plan_harmonization(fa, gtf)
        assert plan is not None
        assert plan.rename_map == {"1": "chr1", "2": "chr2", "MT": "chrM"}


# ===========================================================================
# Part 2 — harmonize_gtf
# ===========================================================================


class TestHarmonizeGtf:

    # --- closed-loop (CRITICAL) ------------------------------------------

    def test_closed_loop_add_chr_resolves_mismatch(self, tmp_path):
        """harmonize GTF (add_chr) then check_reference_consistency == [] ."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("1", "2"))
        out = tmp_path / "harmonized.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        assert check_reference_consistency(fa, out) == []

    def test_closed_loop_strip_chr_resolves_mismatch(self, tmp_path):
        """harmonize GTF (strip_chr) then check_reference_consistency == [] ."""
        fa = _write(tmp_path / "ref.fa", _fasta("1", "2"))
        gtf = _write(tmp_path / "genes.gtf", _gtf("chr1", "chr2"))
        out = tmp_path / "harmonized.gtf"
        harmonize_gtf(gtf, "strip_chr", out)
        assert check_reference_consistency(fa, out) == []

    # --- column fidelity -------------------------------------------------

    def test_column_fidelity_add_chr(self, tmp_path):
        """Only column 1 changes; everything after the first tab is byte-identical."""
        row = '1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id "g1"\n'
        gtf = _write(tmp_path / "in.gtf", row)
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        result = out.read_text()
        lines = [l for l in result.splitlines(keepends=True) if l.strip() and not l.startswith("#")]
        assert len(lines) == 1
        col1, rest = lines[0].split("\t", 1)
        assert col1 == "chr1"
        assert rest == "source\tgene\t1\t100\t.\t+\t.\t" + 'gene_id "g1"\n'

    def test_column_fidelity_strip_chr(self, tmp_path):
        """strip_chr: only column 1 changes."""
        row = 'chr2\tsource\texon\t5\t50\t.\t-\t.\tgene_id "g2"\n'
        gtf = _write(tmp_path / "in.gtf", row)
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "strip_chr", out)
        result = out.read_text()
        lines = [l for l in result.splitlines(keepends=True) if l.strip() and not l.startswith("#")]
        col1, rest = lines[0].split("\t", 1)
        assert col1 == "2"
        assert rest == "source\texon\t5\t50\t.\t-\t.\t" + 'gene_id "g2"\n'

    # --- pass-through lines -----------------------------------------------

    def test_passthrough_comment_and_blank_and_track_browser(self, tmp_path):
        """Comment, blank, track, and browser lines are passed through unchanged."""
        content = (
            "# comment line\n"
            "\n"
            "track name=foo\n"
            "browser position chr1:1-100\n"
            '1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id "g1"\n'
        )
        gtf = _write(tmp_path / "in.gtf", content)
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        result = out.read_text()
        assert result.startswith("# comment line\n")
        assert "\n\n" in result
        assert "track name=foo\n" in result
        assert "browser position chr1:1-100\n" in result

    # --- line endings -------------------------------------------------------

    def test_crlf_preserved(self, tmp_path):
        """A \\r\\n input file stays \\r\\n."""
        row = '1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id "g1"\r\n'
        gtf = _write(tmp_path / "in.gtf", row)
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        raw = out.read_bytes()
        assert b"\r\n" in raw

    def test_lf_preserved(self, tmp_path):
        """A \\n input file stays \\n (no \\r injected)."""
        row = '1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id "g1"\n'
        gtf = _write(tmp_path / "in.gtf", row)
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        raw = out.read_bytes()
        assert b"\r\n" not in raw
        assert b"\n" in raw

    # --- gzip ---------------------------------------------------------------

    def test_gz_in_gz_out(self, tmp_path):
        """A .gz input → .gz output that decompresses to the harmonized text."""
        text = _gtf("1", "2")
        gtf = _write_gz(tmp_path / "in.gtf.gz", text)
        out = tmp_path / "out.gtf.gz"
        harmonize_gtf(gtf, "add_chr", out)
        with gzip.open(out, "rt") as fh:
            result = fh.read()
        assert "chr1\t" in result
        assert "chr2\t" in result

    def test_plain_in_plain_out(self, tmp_path):
        """Plain input → plain output (no gzip magic bytes)."""
        gtf = _write(tmp_path / "in.gtf", _gtf("1"))
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        raw = out.read_bytes()
        # gzip magic bytes are 1f 8b
        assert not raw.startswith(b"\x1f\x8b")

    # --- idempotence / both directions -----------------------------------

    def test_add_chr_already_prefixed_is_idempotent(self, tmp_path):
        """add_chr on a seqname that already starts with chr leaves it unchanged."""
        gtf = _write(tmp_path / "in.gtf", _gtf_row("chr1"))
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        result = out.read_text()
        col1 = result.split("\t", 1)[0]
        assert col1 == "chr1"

    def test_strip_chr_already_bare_is_idempotent(self, tmp_path):
        """strip_chr on a seqname without chr prefix leaves it unchanged."""
        gtf = _write(tmp_path / "in.gtf", _gtf_row("1"))
        out = tmp_path / "out.gtf"
        harmonize_gtf(gtf, "strip_chr", out)
        result = out.read_text()
        col1 = result.split("\t", 1)[0]
        assert col1 == "1"

    def test_harmonize_gtf_returns_path(self, tmp_path):
        """harmonize_gtf returns a Path object equal to out_path."""
        gtf = _write(tmp_path / "in.gtf", _gtf("1"))
        out = tmp_path / "out.gtf"
        result = harmonize_gtf(gtf, "add_chr", out)
        assert result == out
        assert isinstance(result, Path)

    # --- whitespace-padded seqname (strip-parity with gtf_contigs) -----------

    def test_closed_loop_add_chr_whitespace_seqname(self, tmp_path):
        """GTF seqname with leading/trailing whitespace (' 1 ') is still harmonized
        to match FASTA 'chr1': the closed loop holds even for whitespace-padded col1."""
        fa = _write(tmp_path / "ref.fa", _fasta("chr1", "chr2"))
        # seqnames have leading space — a malformed but real-world edge case
        gtf_text = " 1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"g1\"\n"
        gtf_text += " 2\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"g2\"\n"
        gtf = _write(tmp_path / "genes.gtf", gtf_text)
        out = tmp_path / "harmonized.gtf"
        harmonize_gtf(gtf, "add_chr", out)
        assert check_reference_consistency(fa, out) == []

    def test_closed_loop_strip_chr_whitespace_seqname(self, tmp_path):
        """GTF seqname with leading whitespace (' chr1') is still harmonized
        to match bare FASTA '1': the closed loop holds in both directions."""
        fa = _write(tmp_path / "ref.fa", _fasta("1", "2"))
        gtf_text = " chr1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"g1\"\n"
        gtf_text += " chr2\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"g2\"\n"
        gtf = _write(tmp_path / "genes.gtf", gtf_text)
        out = tmp_path / "harmonized.gtf"
        harmonize_gtf(gtf, "strip_chr", out)
        assert check_reference_consistency(fa, out) == []
