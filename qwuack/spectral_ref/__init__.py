"""Independent high-precision Riemann reference (mpmath).

This is NOT the production Signal Processor engine.
It is a mathematical reference for validation only.
"""

from qwuack.spectral_ref.reference import (
    REFERENCE_ENGINE_VERSION,
    ODLYZKO_ZEROS,
    set_precision,
    hardy_z_reference,
    zeta_reference,
    zero_ordinate_reference,
    evaluate_fixture_point,
)

__all__ = [
    "REFERENCE_ENGINE_VERSION",
    "ODLYZKO_ZEROS",
    "set_precision",
    "hardy_z_reference",
    "zeta_reference",
    "zero_ordinate_reference",
    "evaluate_fixture_point",
]
