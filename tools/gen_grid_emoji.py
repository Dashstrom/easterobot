"""Generate grid emoji for chess or skyjo."""  # noqa: INP001

import pathlib
from string import ascii_uppercase

from PIL import Image, ImageDraw, ImageFont

LETTERS = list(ascii_uppercase)
DIGITS = [str(n) for n in range(1, 13)]
HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
FONT = HERE / "gg sans Bold.ttf"
PLACEMENTS = ROOT / "easterobot" / "resources" / "emotes" / "placements"
SKYJO = ROOT / "easterobot" / "resources" / "emotes" / "skyjo"
BLUE = (59, 136, 195)


def average_y(
    texts: list[str],
    font: ImageFont.FreeTypeFont,
) -> float:
    """Compute averages size."""
    y_paddings = []
    im_example = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw_example = ImageDraw.Draw(im_example)
    for char in texts:
        _, y, _, h = draw_example.textbbox((0, 0), char, font)
        y_paddings.append((128 - h - y) // 2)
    return y_paddings[len(y_paddings) // 2]


def case_emoji(
    text: str,
    color: tuple[int, int, int],
    y: float,
    font: ImageFont.FreeTypeFont,
) -> Image.Image:
    """Case emoji."""
    im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    x, _, w, __ = draw.textbbox((0, 0), text, font)
    draw.ellipse((0, 0, 30, 30), fill=color)
    draw.ellipse((97, 0, 127, 30), fill=color)
    draw.ellipse((0, 97, 30, 127), fill=color)
    draw.ellipse((97, 97, 127, 127), fill=color)
    draw.rectangle((0, 15, 127, 112), fill=color)
    draw.rectangle((15, 0, 112, 127), fill=color)
    x = (128 - w - x) // 2
    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    return im.quantize(colors=8)


def gen_grid_emoji() -> None:
    """Generate grid emoji."""
    PLACEMENTS.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(FONT, 110)
    y_median = average_y(list(LETTERS + DIGITS), font)
    for char in LETTERS + DIGITS:
        place = f"{char}"
        im = case_emoji(place, BLUE, y_median, font)
        dest = PLACEMENTS / f"s{place}.png"
        im.save(dest, optimize=True)
        print(dest, dest.stat().st_size)  # noqa: T201
    dest = PLACEMENTS / "s_.png"
    im = case_emoji(" ", BLUE, y_median, font)
    im.save(dest, optimize=True)
    print(dest, dest.stat().st_size)  # noqa: T201

    SKYJO.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(FONT, 100)
    values = list(range(-2, 13))
    texts = list(map(str, values))
    y_median = average_y(texts, font)
    for value in values:
        if value < 0:
            color = (44, 26, 110)
        elif value == 0:
            color = (47, 175, 230)
        elif value <= 4:  # noqa: PLR2004
            color = (90, 156, 9)
        elif value <= 8:  # noqa: PLR2004
            color = (238, 209, 29)
        elif value <= 12:  # noqa: PLR2004
            color = (232, 13, 0)
        im = case_emoji(str(value), color, y_median, font)
        name = f"m{-value}" if value < 0 else f"p{value}"
        dest = SKYJO / f"skyjo_{name}.png"
        im.save(dest, optimize=True)
        print(dest, dest.stat().st_size)  # noqa: T201
    gray = (165, 156, 148)
    im = case_emoji("?", gray, y_median, font)
    dest = SKYJO / "skyjo_back.png"
    im.save(dest, optimize=True)
    print(dest, dest.stat().st_size)  # noqa: T201


if __name__ == "__main__":
    gen_grid_emoji()
