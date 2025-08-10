"""Luck calculation system for hunt discovery and spotting mechanics.

This module manages probability calculations for players discovering eggs and
being spotted during hunts. It implements luck-based modifiers that depend on
egg count, sleep hours, and configuration shields to provide balanced gameplay.
"""

import logging
from dataclasses import dataclass

from easterobot.config import RAND, MConfig

logger = logging.getLogger(__name__)


@dataclass
class HuntLuck:
    """Manages luck-based probabilities for hunt events."""

    egg_count: int
    luck: float
    sleep_hours: bool
    config: MConfig

    @property
    def discovered(self) -> float:
        """Calculate the probability of successfully discovering an egg.

        Players with fewer eggs than the shield threshold have 100% discovery
        rate. Otherwise, probability is based on luck factor and reduced during
        sleep hours.

        Returns:
            Discovery probability as a float between 0.0 and 1.0.
        """
        if self.egg_count <= self.config.commands.search.discovered.shield:
            return 1.0
        discovery_probability = (
            self.config.commands.search.discovered.probability(self.luck)
        )
        if self.sleep_hours:
            discovery_probability /= self.config.sleep.divide_discovered
        return discovery_probability

    @property
    def spotted(self) -> float:
        """Calculate the probability of being spotted during a hunt attempt.

        Players with fewer eggs than the shield threshold are never spotted.
        Otherwise, probability is based on luck factor and reduced during
        sleep hours.

        Returns:
            Spotted probability as a float between 0.0 and 1.0.
        """
        if self.egg_count <= self.config.commands.search.spotted.shield:
            return 0.0
        spotted_probability = self.config.commands.search.spotted.probability(
            self.luck
        )
        if self.sleep_hours:
            spotted_probability /= self.config.sleep.divide_spotted
        return spotted_probability

    def sample_discovered(self) -> bool:
        """Determine if a player successfully discovers an egg.

        Generates a random number and compares it against the discovery
        probability to determine success.
        Logs the comparison for debugging purposes.

        Returns:
            True if the player discovers an egg, False otherwise.
        """
        random_sample = RAND.random()
        discovery_threshold = self.discovered
        logger.info(
            "discovered: expect over %.4f got %.4f",
            discovery_threshold,
            random_sample,
        )
        return discovery_threshold > random_sample

    def sample_spotted(self) -> bool:
        """Determine if a player gets spotted during hunt attempt.

        Generates a random number and compares it against the spotted
        probability to determine if the player is caught.
        Logs the comparison for debugging.

        Returns:
            True if the player is spotted, False otherwise.
        """
        random_sample = RAND.random()
        spotted_threshold = self.spotted
        logger.info(
            "spotted: expect over %.4f got %.4f",
            spotted_threshold,
            random_sample,
        )
        return spotted_threshold > random_sample
