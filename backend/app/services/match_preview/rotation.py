"""Line-up rotation: how many of today's starters were not in the previous match's XI."""

from __future__ import annotations

from typing import Optional, Sequence

from app.services.match_preview.schemas import PlayerRef

STARTING_XI_SIZE = 11


def _key(player: PlayerRef) -> Optional[str]:
    if player.id:
        return f"id:{player.id}"
    if player.name and player.name.strip():
        return f"name:{player.name.strip().casefold()}"
    return None


def compute_rotation(
    today: Sequence[PlayerRef], previous: Sequence[PlayerRef]
) -> tuple[int, list[PlayerRef], list[PlayerRef]]:
    """-> (changes, came_in, dropped_out).

    ``changes`` = today's starters whose id (name when the id is missing) is not in the
    previous XI. ``came_in`` lists those players, ``dropped_out`` the previous starters
    who are not in today's XI. Both lists need a full XI; the caller checks that."""
    previous_keys = {k for k in (_key(p) for p in previous) if k}
    today_keys = {k for k in (_key(p) for p in today) if k}
    came_in = [p for p in today if (_key(p) or "") not in previous_keys]
    dropped_out = [p for p in previous if (_key(p) or "") not in today_keys]
    return len(came_in), came_in, dropped_out


def rotation_problem(today: Sequence[PlayerRef], previous: Sequence[PlayerRef]) -> Optional[str]:
    """Turkish reason why a rotation count cannot be given, or None when both XIs are complete."""
    if len(today) != STARTING_XI_SIZE:
        return f"Bugünkü ilk 11 eksik ({len(today)} oyuncu)."
    if len(previous) != STARTING_XI_SIZE:
        return f"Önceki maçın ilk 11'i eksik ({len(previous)} oyuncu)."
    if any(_key(p) is None for p in [*today, *previous]):
        return "Oyuncu kimlikleri eksik, karşılaştırma yapılamadı."
    return None
