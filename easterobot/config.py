"""Main program."""
import random
from pathlib import Path
from typing import Any, Optional, Tuple, cast

import discord
import yaml

RAND = random.SystemRandom()


class Action:
    """Represent a possible action."""

    def __init__(self, data: Any, conf: "Config") -> None:
        self._data = data
        self._config = conf

    def text(self) -> str:
        """Text used to describe action."""
        return cast(str, self._data["text"])

    def fail_text(self, member: discord.Member) -> str:
        """Text to print if action is failed."""
        return self._config.conjugate(
            self._data.get("fail", {}).get("text", ""), member
        )

    def fail_gif(self) -> str:
        """Gif to print if action is failed."""
        return cast(str, self._data.get("fail", {}).get("gif", ""))

    def success_text(self, member: discord.Member) -> str:
        """Text to print if action is success."""
        return self._config.conjugate(
            self._data.get("success", {}).get("text", ""), member
        )

    def success_gif(self) -> str:
        """Gif to print if action is success."""
        return cast(str, self._data.get("success", {}).get("gif", ""))


class Command:
    """Represent a possible action."""

    def __init__(self, data: Any, conf: "Config") -> None:
        self._data = data
        self._config = conf


class Config:
    def __init__(self, config_path: Path) -> None:
        with config_path.open("r", encoding="utf8") as file:
            self._data = yaml.safe_load(file)

    @property
    def guild_id(self) -> int:
        return cast(int, self._data["guild"])

    @property
    def admin_ids(self) -> Tuple[int, ...]:
        return cast(Tuple[int, ...], tuple(self._data["admins"]))

    @property
    def token(self) -> int:
        return cast(int, self._data["token"])

    @property
    def database(self) -> str:
        return cast(str, self._data["database"])

    @property
    def group(self) -> str:
        return cast(str, self._data["group"])

    def command_attr(self, name: str, key: str) -> Any:
        return cast(float, self._data["commands"][name][key])

    def hunt_cooldown(self) -> float:
        min_ = self._data["hunt"]["cooldown"]["min"]
        max_ = self._data["hunt"]["cooldown"]["max"]
        min_, max_ = min(min_, max_), max(min_, max_)
        return cast(float, min_ + RAND.random() * (max_ - min_))

    def hunt_timeout(self) -> float:
        return cast(float, self._data["hunt"]["timeout"])

    def hunt_weight_egg(self) -> float:
        return cast(float, self._data["hunt"]["weights"]["egg"])

    def hunt_weight_speed(self) -> float:
        return cast(float, self._data["hunt"]["weights"]["speed"])

    @property
    def woman_id(self) -> int:
        return cast(int, self._data["woman_id"])

    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(
            name="_", animated=False, id=RAND.choice(self._data["emojis"])
        )

    def emojis(self) -> Tuple[discord.PartialEmoji, ...]:
        return tuple(
            discord.PartialEmoji(name="_", animated=False, id=emoji_id)
            for emoji_id in self._data["emojis"]
        )

    def action(self) -> Action:
        return Action(RAND.choice(self._data["action"]), self)

    def appear(self) -> str:
        return cast(str, RAND.choice(self._data["appear"]))

    def spotted(self, member: discord.Member) -> str:
        return self.conjugate(
            RAND.choice(self._data["spotted"]), member=member
        )

    def hidden(self, member: discord.Member) -> str:
        return self.conjugate(RAND.choice(self._data["hidden"]), member)

    def failed(self, member: discord.Member) -> str:
        return self.conjugate(RAND.choice(self._data["failed"]), member)

    def conjugate(self, text: str, member: discord.Member) -> str:
        if any(
            role.name.lower() in ("woman", "girl", "femme", "fille")
            for role in member.roles
        ):
            key = "woman"
        else:
            key = "man"
        for term, versions in self._data["conjugate"].items():
            word = versions.get(key, "")
            text = text.replace("{" + term.lower() + "}", word.lower())
            text = text.replace("{" + term.upper() + "}", word.upper())
            text = text.replace("{" + term.title() + "}", word.title())
        text = text.replace("{user}", f"<@{member.id}>")
        return text


def agree(
    singular: str,
    plural: str,
    /,
    amount: Optional[int],
    *args: Any,
) -> str:
    if amount is None or amount in (-1, 0, 1):
        return singular.format(amount, *args)
    return plural.format(amount, *args)
