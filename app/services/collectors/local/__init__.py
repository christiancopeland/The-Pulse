"""
Local Government Collectors for The Pulse.

Collectors for Hamilton County TN and Catoosa/Walker County GA.
"""

from .hamilton_county import (
    HamiltonCouncilCollector,
    HamiltonPropertyCollector,
    ChattanoogaPermitCollector,
    HamiltonCourtCollector
)
from .georgia_counties import (
    CatoosaCountyCollector,
    WalkerCountyCollector
)

__all__ = [
    'HamiltonCouncilCollector',
    'HamiltonPropertyCollector',
    'ChattanoogaPermitCollector',
    'HamiltonCourtCollector',
    'CatoosaCountyCollector',
    'WalkerCountyCollector',
]


def get_local_collectors():
    """Get all local government collectors."""
    return [
        HamiltonCouncilCollector(),
        HamiltonPropertyCollector(),
        ChattanoogaPermitCollector(),
        HamiltonCourtCollector(),
        CatoosaCountyCollector(),
        WalkerCountyCollector(),
    ]
