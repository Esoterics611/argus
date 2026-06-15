"""Stealth swap-seam — select a browser backend by name."""

from argus.core.stealth.backends import (
    Backend,
    CamoufoxBackend,
    PatchrightBackend,
    StealthBackend,
    VanillaBackend,
)

__all__ = [
    "Backend",
    "VanillaBackend",
    "StealthBackend",
    "PatchrightBackend",
    "CamoufoxBackend",
    "get_backend",
]

_REGISTRY: dict[str, type[Backend]] = {
    "vanilla": VanillaBackend,
    "stealth": StealthBackend,
    "patchright": PatchrightBackend,
    "camoufox": CamoufoxBackend,
}


def get_backend(name: str) -> Backend:
    """Return a backend instance for *name* (vanilla|stealth|patchright|camoufox)."""
    name = name.lower()
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown stealth backend: {name!r}. Choose from {list(_REGISTRY)}")
    return cls()
