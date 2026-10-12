"""Keep historical byte pins exact across the owner's mechanical product rename.

This is a test-only comparison with recorded bytes, never certification of the
renamed producer or study source. Their live qualification still requires evidence.
"""

from __future__ import annotations


def original_product_name(text: str) -> str:
    """Restore only the three product-name spellings for historical hash checks."""
    return (
        text.replace("Compass", "Cargento")
        .replace("COMPASS", "CARGENTO")
        .replace("compass", "cargento")
    )
