"""Defense mitigation strategies to handle detected Crescendo escalation triggers."""
from .strategy_a import ContextCondensationStrategy
from .strategy_b import BacktrackingPerturbationStrategy

__all__ = ["ContextCondensationStrategy", "BacktrackingPerturbationStrategy"]
