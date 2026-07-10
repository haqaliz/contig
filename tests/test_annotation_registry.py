from contig.cli import _inject_default_params
from contig.registry import select_pipeline


def test_germline_default_params_enable_vep():
    entry = select_pipeline("variant_calling")
    assert "vep" in str(entry.default_params.get("tools", ""))


def test_inject_does_not_override_user_tools():
    params = {"tools": "haplotypecaller"}  # user chose their own tools
    _inject_default_params(params, "variant_calling")
    assert params["tools"] == "haplotypecaller"  # user value preserved


def test_inject_adds_default_when_absent():
    params = {}
    _inject_default_params(params, "variant_calling")
    assert "vep" in str(params.get("tools", ""))


def test_somatic_default_params_enable_vep():
    entry = select_pipeline("somatic_variant_calling")
    tools = str(entry.default_params.get("tools", ""))
    assert "vep" in tools
    assert "strelka" in tools
    assert "mutect2" in tools


def test_inject_does_not_override_user_tools_somatic():
    params = {"tools": "strelka"}  # user chose their own tools
    _inject_default_params(params, "somatic_variant_calling")
    assert params["tools"] == "strelka"  # user value preserved
