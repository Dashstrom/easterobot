"""Luck module."""

import logging
from dataclasses import dataclass

from easterobot.config import RAND, MConfig

logger = logging.getLogger(__name__)


@dataclass
class HuntLuck:
    egg_count: int
    luck: float
    sleep_hours: bool
    config: MConfig

    @property
    def discovered(self) -> float:
        """Discovered probability."""
        if self.egg_count <= self.config.commands.search.discovered.shield:
            return 1.0
        prob = self.config.commands.search.discovered.probability(self.luck)
        if self.sleep_hours:
            prob /= self.config.sleep.divide_discovered
        return prob

    @property
    def spotted(self) -> float:
        """Spotted probability."""
        if self.egg_count <= self.config.commands.search.spotted.shield:
            return 0.0
        prob = self.config.commands.search.spotted.probability(self.luck)
        if self.sleep_hours:
            prob /= self.config.sleep.divide_spotted
        return prob

    def sample_discovered(self) -> bool:
        """Get if player get detected."""
        sample = RAND.random()
        discovered = self.discovered
        logger.info(
            "discovered: expect over %.4f got %.4f",
            discovered,
            sample,
        )
        return discovered > sample

    def sample_spotted(self) -> bool:
        """Get if player get spotted."""
        sample = RAND.random()
        spotted = self.spotted
        logger.info(
            "spotted: expect over %.4f got %.4f",
            spotted,
            sample,
        )
        return spotted > sample
