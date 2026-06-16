"""Response-contract version.

Bumped on any change to the response envelope (additive or breaking). Surfaced as
``meta.version`` on every envelope and via ``GET /v1/version``, and folded into the
ETag so caches invalidate uniformly when the contract changes.
"""

RESPONSE_VERSION = "1.1.0"
