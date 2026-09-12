"""Derive valid directed routes from a line's ordered stop list.

The API lists every stop a boat calls at, in order, including the return leg
(e.g. Stavsnäs → Sandhamn → Telegrafholmen → ... → Sandhamn → Stavsnäs). A
directed route origin → destination is valid when destination appears after
some occurrence of origin. We never assume symmetric traffic.
"""

from __future__ import annotations

from collections.abc import Mapping

from .models import BattaxiLine, BattaxiPier, BattaxiRoute


def unique_stops(line: BattaxiLine) -> list[str]:
    """Return the line's stop ids in first-appearance order, without duplicates."""
    return list(dict.fromkeys(line.stops))


def destination_pier_ids(line: BattaxiLine, origin_id: str) -> list[str]:
    """Return pier ids reachable after boarding at origin_id, in stop order."""
    reachable: dict[str, None] = {}
    seen_origin = False
    for stop in line.stops:
        if stop == origin_id:
            seen_origin = True
        elif seen_origin:
            reachable.setdefault(stop, None)
    return list(reachable)


def origin_pier_ids(line: BattaxiLine) -> list[str]:
    """Return pier ids that have at least one reachable destination."""
    return [stop for stop in unique_stops(line) if destination_pier_ids(line, stop)]


def build_route(
    line: BattaxiLine,
    piers_by_id: Mapping[str, BattaxiPier],
    origin_id: str,
    destination_id: str,
) -> BattaxiRoute:
    """Build a route, validating that the pair is served by the line."""
    if destination_id not in destination_pier_ids(line, origin_id):
        raise ValueError(f"{line.name} does not serve {origin_id} → {destination_id}")
    try:
        origin = piers_by_id[origin_id]
        destination = piers_by_id[destination_id]
    except KeyError as err:
        raise ValueError(f"Unknown pier id {err}") from err
    return BattaxiRoute(
        line_id=line.id,
        line_name=line.name,
        origin_id=origin.id,
        origin_name=origin.name,
        destination_id=destination.id,
        destination_name=destination.name,
    )
