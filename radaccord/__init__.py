"""RadAccord's optional native-engine audit entry points.

Importing this module does not import or initialise a radiomics engine.
"""

__version__ = "1.2.0rc3"
__all__ = ["__version__", "audit_pyradiomics", "audit_mirp"]


def audit_pyradiomics(image, mask, *, config=None, label=1):
    """Run the PyRadiomics adapter; its optional dependencies are loaded on use."""
    from .pyradiomics import audit_pyradiomics as audit
    return audit(image, mask, config=config, label=label)


def audit_mirp(image, mask, *, config=None, label=1):
    """Run the MIRP adapter; its optional dependencies are loaded on use."""
    from .mirp import audit_mirp as audit
    return audit(image, mask, config=config, label=label)
