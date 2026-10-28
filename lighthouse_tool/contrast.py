import json
import re
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from lighthouse_tool.repo import Parser, Refusal

SOURCES = ("declared", "tree", "pixels")
EXACT_SOURCES = ("declared", "tree")
NORMAL_THRESHOLD = 4.5
LARGE_THRESHOLD = 3.0
PIXEL_MARGIN = 0.3
OPAQUE = 255
COLOUR_FORMS = "#RGB, #RRGGBB, #RRGGBBAA, 0xRRGGBB, 0xAARRGGBB or rgb(r, g, b)"

HASH_COLOUR = re.compile(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})")
FLUTTER_COLOUR = re.compile(r"0[xX]([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})")
RGB_COLOUR = re.compile(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)")


class Colour(NamedTuple):
    red: int
    green: int
    blue: int
    alpha: int


def hex_pairs(digits: str) -> List[int]:
    return [int(digits[index:index + 2], 16) for index in range(0, len(digits), 2)]


def hash_colour(digits: str) -> Colour:
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    values = hex_pairs(digits)
    alpha = values[3] if len(values) == 4 else OPAQUE
    return Colour(values[0], values[1], values[2], alpha)


def flutter_colour(digits: str) -> Colour:
    values = hex_pairs(digits)
    if len(values) == 4:
        return Colour(values[1], values[2], values[3], values[0])
    return Colour(values[0], values[1], values[2], OPAQUE)


def rgb_colour(text: str, parts: Tuple[str, ...]) -> Colour:
    values = [int(part) for part in parts]
    if any(value > 255 for value in values):
        raise Refusal("cannot read the colour {}: rgb channels run from 0 to 255".format(text))
    return Colour(values[0], values[1], values[2], OPAQUE)


def read_colour(text: str) -> Colour:
    stripped = text.strip()
    hashed = HASH_COLOUR.fullmatch(stripped)
    if hashed:
        return hash_colour(hashed.group(1))
    flutter = FLUTTER_COLOUR.fullmatch(stripped)
    if flutter:
        return flutter_colour(flutter.group(1))
    rgb = RGB_COLOUR.fullmatch(stripped)
    if rgb:
        return rgb_colour(text, rgb.groups())
    raise Refusal("cannot read the colour {}: write it as {}".format(text, COLOUR_FORMS))


def linear_channel(value: int) -> float:
    fraction = value / 255
    if fraction <= 0.04045:
        return fraction / 12.92
    return ((fraction + 0.055) / 1.055) ** 2.4


def relative_luminance(colour: Colour) -> float:
    return (
        0.2126 * linear_channel(colour.red)
        + 0.7152 * linear_channel(colour.green)
        + 0.0722 * linear_channel(colour.blue)
    )


def contrast_ratio(foreground: Colour, background: Colour) -> float:
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def undecided_reason(foreground: Colour, background: Colour, source: str, ratio: float, threshold: float) -> Optional[str]:
    if foreground.alpha < OPAQUE or background.alpha < OPAQUE:
        return "a translucent colour has no single contrast ratio without the colour beneath it"
    if source not in EXACT_SOURCES and abs(ratio - threshold) <= PIXEL_MARGIN:
        return "a pixel sample within {} of the {} threshold cannot decide pass or fail".format(PIXEL_MARGIN, threshold)
    return None


def measure(foreground: Colour, background: Colour, source: str, large: bool) -> Dict[str, Any]:
    ratio = contrast_ratio(foreground, background)
    threshold = LARGE_THRESHOLD if large else NORMAL_THRESHOLD
    reason = undecided_reason(foreground, background, source, ratio, threshold)
    result = {
        "ratio": round(ratio, 2),
        "threshold": threshold,
        "status": "could-not-run" if reason else ("pass" if ratio >= threshold else "fail"),
        "source": source,
    }
    return {**result, "reason": reason} if reason else result


def parser() -> Parser:
    arguments = Parser(prog="lighthouse contrast", add_help=False)
    arguments.add_argument("--foreground", required=True)
    arguments.add_argument("--background", required=True)
    arguments.add_argument("--source", required=True, choices=SOURCES)
    arguments.add_argument("--large", action="store_true")
    return arguments


def run(argv: List[str]) -> Tuple[int, Optional[str], Optional[str]]:
    try:
        options = parser().parse_args(argv[1:])
        foreground = read_colour(options.foreground)
        background = read_colour(options.background)
    except Refusal as refusal:
        return 2, json.dumps({"error": str(refusal)}), "lighthouse contrast: {}".format(refusal)
    return 0, json.dumps(measure(foreground, background, options.source, options.large)), None
