"""
The prompt registry (Phase 1 remediation, WP-3).

Importing this package registers every prompt in the codebase. That
matters: the lock-file and snapshot tests walk `REGISTRY.all()`, so a
prompt defined in a module nobody imports would be silently uncovered by
both. Adding a prompt module means adding it here.

See `core.py` for why identity is split across a content hash, a
semantic version, and a committed snapshot.
"""

from app.prompts.core import (
    REGISTRY,
    Prompt,
    PromptRegistry,
    content_hash_of,
    get,
    register,
)

# Registration by import. Ordered by pipeline stage, not alphabetically,
# so the list reads as the pipeline it describes.
from app.prompts import (  # noqa: E402,F401  (imported for side effects)
    analysis,
    generation,
    library,
    validation,
)

__all__ = [
    "REGISTRY",
    "Prompt",
    "PromptRegistry",
    "content_hash_of",
    "get",
    "register",
]
