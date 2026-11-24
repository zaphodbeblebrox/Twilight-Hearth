"""Small parser that splits "1 1/2 cups flour" into quantity, unit and the rest.

It only needs to be good enough for scaling; the original text is always kept.
"""

import re
import unicodedata
from fractions import Fraction

UNITS = {
    "teaspoon": "tsp teaspoon teaspoons",
    "tablespoon": "tbsp tbs tablespoon tablespoons",
    "cup": "c cup cups",
    "ounce": "oz ounce ounces",
    "pound": "lb lbs pound pounds",
    "gram": "g gram grams",
    "kilogram": "kg kilogram kilograms",
    "milliliter": "ml milliliter milliliters millilitre millilitres",
    "liter": "l liter liters litre litres",
    "pint": "pt pint pints",
    "quart": "qt quart quarts",
    "gallon": "gal gallon gallons",
    "pinch": "pinch pinches",
    "dash": "dash dashes",
    "clove": "clove cloves",
    "can": "can cans",
    "slice": "slice slices",
    "stick": "stick sticks",
    "package": "pkg package packages",
}
LOOKUP = {alias: unit for unit, aliases in UNITS.items() for alias in aliases.split()}

NUMBER = r"(?:[0-9]+\s+[0-9]+/[0-9]+|[0-9]+/[0-9]+|[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
QUANTITY = re.compile(
    rf"^\s*(?P<low>{NUMBER})(?:\s*(?:-|to\b)\s*(?P<high>{NUMBER}))?(?P<rest>.*)$", re.S
)


def _plain(text: str) -> str:
    out: list[str] = []
    for char in text:
        if unicodedata.name(char, "").startswith("VULGAR FRACTION"):
            value = unicodedata.normalize("NFKC", char).replace("⁄", "/")
            # "1½" means 1 1/2, so keep the parts apart.
            out.append(f" {value}" if out and out[-1].isdigit() else value)
        else:
            out.append({"⁄": "/", "–": "-", "—": "-"}.get(char, char))
    return "".join(out)


def _number(text: str) -> Fraction | None:
    try:
        return sum((Fraction(part) for part in text.split()), Fraction(0))
    except (ValueError, ZeroDivisionError):
        return None


def parse(text: str) -> dict[str, str | None]:
    empty = {"quantity": None, "quantity_max": None, "unit": None, "food": text.strip()}
    match = QUANTITY.match(_plain(text))
    if not match:
        return empty
    low = _number(match["low"])
    high = _number(match["high"]) if match["high"] else None
    rest = match["rest"]
    # "2% milk" and "2-inch piece" are descriptions rather than amounts.
    if low is None or (match["high"] and high is None) or re.match(r"[%/\-\d.]", rest):
        return empty
    rest = rest.strip()
    unit = None
    if word := re.match(r"([A-Za-z]+)\.?(?=\s|$)", rest):
        # A capital T is the usual shorthand for tablespoon, and t for teaspoon.
        unit = {"T": "tablespoon", "t": "teaspoon"}.get(word[1]) or LOOKUP.get(word[1].lower())
        if unit:
            rest = re.sub(r"^of\s+", "", rest[word.end() :].strip())
    return {
        "quantity": str(low),
        "quantity_max": str(high) if high is not None else None,
        "unit": unit,
        "food": rest,
    }
