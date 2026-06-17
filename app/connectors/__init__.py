"""Connector package. Importing it registers every connector via @register.

To add a source: create a module here with an @register Connector subclass and
import it below. The router discovers it automatically.
"""

from . import (  # noqa: F401
    arxiv,
    esco,
    gdelt,
    github,
    mitre_attack,
    nvd,
    sec_edgar,
    stackexchange,
    wikidata,
    wikipedia,
)

__all__ = [
    "wikipedia",
    "wikidata",
    "stackexchange",
    "github",
    "nvd",
    "mitre_attack",
    "arxiv",
    "sec_edgar",
    "esco",
    "gdelt",
]
