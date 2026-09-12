"""Tests that the translation files are complete and consistent."""

import json
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from custom_components.stavsnas_battaxi.const import DOMAIN

TRANSLATIONS = (
    Path(__file__).parent.parent
    / "custom_components"
    / "stavsnas_battaxi"
    / "translations"
)


def _keys(obj: object, prefix: str = "") -> set[str]:
    if not isinstance(obj, dict):
        return {prefix}
    return {
        key for name, value in obj.items() for key in _keys(value, f"{prefix}.{name}")
    }


def test_swedish_and_english_have_the_same_keys() -> None:
    en = json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8"))
    sv = json.loads((TRANSLATIONS / "sv.json").read_text(encoding="utf-8"))
    assert _keys(en) == _keys(sv)


async def test_swedish_entity_names_are_loaded(hass: HomeAssistant) -> None:
    translations = await async_get_translations(hass, "sv", "entity", {DOMAIN})
    assert (
        translations[f"component.{DOMAIN}.entity.sensor.next_departure.name"]
        == "Nästa avgång"
    )
    assert (
        translations[f"component.{DOMAIN}.entity.binary_sensor.bookable.name"]
        == "Bokningsbar"
    )
