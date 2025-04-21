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
        prob = self.config.commands.search.discovered.probability(self.luck)
        if self.sleep_hours:
            prob /= self.config.sleep.divide_discovered
        return prob

    @property
    def spotted(self) -> float:
        """Spotted probability."""
        prob = self.config.commands.search.spotted.probability(self.luck)
        if self.sleep_hours:
            prob /= self.config.sleep.divide_spotted
        return prob

    def sample_discovered(self) -> bool:
        """Get if player get detected."""
        if self.egg_count <= self.config.commands.search.discovered.shield:
            logger.info("discovered: shield with %s eggs", self.egg_count)
            return True
        sample = RAND.random()
        logger.info(
            "discovered: expect over %.2f got %.2f",
            self.discovered,
            sample,
        )
        return self.discovered > sample

    def sample_spotted(self) -> bool:
        """Get if player get spotted."""
        if self.egg_count <= self.config.commands.search.spotted.shield:
            logger.info("spotted: shield with %s eggs", self.egg_count)
            return True
        sample = RAND.random()
        return self.spotted < sample
