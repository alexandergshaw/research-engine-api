"""Preformatted attribution so consumers never parse license codes themselves.

`attribution_line` renders "Display Name — License — URL"; `requires_attribution`
decides whether a license obliges attribution (CC0 / public-domain → no, everything
else → yes, conservatively).
"""

from __future__ import annotations

_DISPLAY = {
    "wikipedia": "Wikipedia",
    "wikidata": "Wikidata",
    "stackexchange": "Stack Exchange",
    "github": "GitHub",
    "nvd": "NVD",
    "mitre_attack": "MITRE ATT&CK",
    "arxiv": "arXiv",
    "sec_edgar": "SEC EDGAR",
    "esco": "ESCO",
    "gdelt": "GDELT",
}


def display_name(name: str) -> str:
    if name in _DISPLAY:
        return _DISPLAY[name]
    if "." in name:  # a publisher domain (e.g. reuters.com) — show verbatim
        return name
    return name.replace("_", " ").title()


def requires_attribution(license_: str | None) -> bool:
    """Conservative: only public-domain / CC0 are attribution-free."""
    if not license_:
        return False
    low = license_.lower()
    if "cc0" in low or "public domain" in low:
        return False
    return True


def attribution_line(name: str, license_: str | None, url: str | None) -> str:
    parts = [display_name(name)]
    if license_:
        parts.append(license_)
    if url:
        parts.append(url)
    return " — ".join(parts)


def any_required(source_dicts: list[dict]) -> bool:
    return any(requires_attribution(d.get("license")) for d in source_dicts)
