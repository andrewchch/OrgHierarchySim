"""Ladder Lab: an agent-based organisation evolution simulator."""

__version__ = "0.1.0"

from .config import Config, FirmStrategy, baseline_config
from .simulation import Simulation

__all__ = ["Config", "FirmStrategy", "Simulation", "baseline_config"]
