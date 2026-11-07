"""Optional gnomAD GraphQL client with a local cache.

The API is per-variant; this is intended for a filtered panel, not a whole
exome. A hard site cap prevents accidental request floods.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Protocol

from contig.variants.models import FrequencyEvidence, SourceProvenance, VariantKey

GNOMAD_MAX_SITES = 1000
GNOMAD_URL = "https://gnomad.broadinstitute.org/api"


class GnomadClient(Protocol):
    def fetch(self, variant_id: str) -> dict | None: ...


class GraphQLGnomadClient:
    def __init__(self, url: str = GNOMAD_URL, dataset: str = "gnomad_r4", timeout: int = 30):
        self.url = url
        self.dataset = dataset
        self.timeout = timeout

    def fetch(self, variant_id: str) -> dict | None:
        query = (
            f'{{ variant(dataset: {self.dataset}, variantId: "{variant_id}") '
            "{ genome { ac an af } exome { ac an af } } }"
        )
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"query": query}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - surface a clear domain error
            raise ValueError(f"gnomAD request failed: {exc}") from exc
        variant = (payload.get("data") or {}).get("variant")
        return variant if isinstance(variant, dict) else None


def _variant_id(key: VariantKey) -> str:
    return f"{key.chrom}-{key.pos}-{key.ref}-{key.alt}"


def _evidence(variant: dict | None) -> FrequencyEvidence | None:
    if not variant:
        return None
    for source in ("genome", "exome"):
        block = variant.get(source)
        if block and block.get("an"):
            return FrequencyEvidence(af=block.get("af"), an=block.get("an"))
    return None


def load_gnomad(
    sites: set[VariantKey],
    client: GnomadClient,
    *,
    cache_path: str | Path | None = None,
    dataset: str = "gnomad_r4",
) -> tuple[dict[VariantKey, FrequencyEvidence], SourceProvenance]:
    if len(sites) > GNOMAD_MAX_SITES:
        raise ValueError(
            f"gnomAD API is limited to {GNOMAD_MAX_SITES} sites; "
            "filter by gene/region or use a frequency TSV"
        )

    cache: dict[str, dict[str, object]] = {}
    if cache_path:
        path = Path(cache_path)
        if path.is_file():
            try:
                cache = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                cache = {}

    evidence: dict[VariantKey, FrequencyEvidence] = {}
    matched = 0
    for key in sites:
        variant_id = _variant_id(key)
        if variant_id in cache:
            cached = cache[variant_id]
            evidence[key] = FrequencyEvidence(af=cached.get("af"), an=cached.get("an"))
            matched += 1
            continue
        variant = client.fetch(variant_id)
        item = _evidence(variant)
        if item is None:
            continue
        evidence[key] = item
        cache[variant_id] = {"af": item.af, "an": item.an}
        matched += 1

    if cache_path:
        Path(cache_path).write_text(json.dumps(cache, indent=2), encoding="utf-8")

    return evidence, SourceProvenance(
        kind="gnomad_api",
        path=str(cache_path or GNOMAD_URL),
        sha256="",
        build=None,
        version=dataset,
        note=f"{matched} of {len(sites)} input sites matched",
    )
