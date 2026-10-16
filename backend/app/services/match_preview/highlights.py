"""Highlights of the match preview: fixed Turkish templates over real numbers.

* Each template has a threshold and fires only when the number is notable.
* Every sentence carries the numbers it is based on (they are also in ``facts``).
* No betting advice, no prediction, no player-quality judgement: the sentences state what
  happened (results, goals, rest days, who is missing, how many changes in the XI).
* History-based templates are skipped for a team whose history could not be verified
  (``history_verified`` False) or that has fewer than the required matches.
* Order: ``importance`` (highest first); at most ``MAX_HIGHLIGHTS`` in total.
"""

from __future__ import annotations

from typing import Optional

from app.services.match_preview.schemas import (
    AbsenteesInfo,
    FormWindow,
    Highlight,
    PreviewSide,
)
from app.services.match_preview.turkish import count_accusative, decimal, join_names

MAX_HIGHLIGHTS = 6
MAX_PER_SIDE = 4

# thresholds (named so the tests and the docs can point at them)
FORM_MIN_PLAYED = 4
FORM_MOSTLY_WON = 4  # 4 wins of 5
FORM_MOSTLY_LOST = 3  # 3 losses of 4-5
GOALS_AGAINST_LOW = 2  # <= 2 goals conceded in 5 matches
GOALS_AGAINST_HIGH = 9  # >= 9 (average 1.8+)
GOALS_FOR_LOW = 2
GOALS_FOR_HIGH = 12  # average 2.4+
XG_MIN_MATCHES = 4
XG_GAP = 3.0  # |goals - xG| over the window
REST_SHORT_DAYS = 3
REST_GAP_DAYS = 3
CONGESTION_MATCHES = 4  # matches in the previous 14 days
ROTATION_CHANGES = 4  # starters who were not in the previous XI
ABSENTEE_NAMES_SHOWN = 4


def _sorted_key(h: Highlight) -> tuple:
    return (-h.importance, h.side != "home", h.id)


def _h(kind: str, side: str, text: str, importance: int, **facts) -> Highlight:
    return Highlight(id=f"{kind}_{side}", kind=kind, side=side, text=text, importance=importance, facts=facts)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- form


def form_statement(team: str, window: FormWindow, where: Optional[str]) -> Optional[tuple[str, int, str, dict]]:
    """-> (polarity, importance, text, facts) for the strongest form statement of a window, or None.

    ``where`` is "evde" / "deplasmanda" for a venue window, None for the all-venues window."""
    n = window.played
    if n < FORM_MIN_PLAYED or window.wins is None or window.losses is None:
        return None
    wins, losses = window.wins, window.losses
    gf, ga = window.goals_for or 0, window.goals_against or 0
    label = f"{where} " if where else ""
    venue_bonus = 0 if where else -8
    facts = {"played": n, "wins": wins, "draws": window.draws, "losses": losses, "goals_for": gf, "goals_against": ga, "where": where or "tümü"}
    score = f"({gf}–{ga})"
    if wins == n:
        return "good", (80 if n >= 5 else 70) + venue_bonus, f"{team} {label}son {n} maçı kazandı {score}.", facts
    if losses == n:
        return "bad", 80 + venue_bonus, f"{team} {label}son {n} maçı kaybetti {score}.", facts
    if n >= 5 and wins >= FORM_MOSTLY_WON:
        return "good", 64 + venue_bonus, f"{team} {label}son {n} maçın {count_accusative(wins)} kazandı {score}.", facts
    if losses >= FORM_MOSTLY_LOST:
        return "bad", 70 + 4 * (losses - 3) + venue_bonus, f"{team} {label}son {n} maçın {count_accusative(losses)} kaybetti {score}.", facts
    if n >= 5 and wins == 0:
        return "bad", 68 + venue_bonus, f"{team} {label}son {n} maçta hiç kazanamadı {score}.", facts
    if n >= 5 and losses == 0 and wins >= 3:
        return "good", 58 + venue_bonus, f"{team} {label}son {n} maçta yenilmedi {score}.", facts
    return None


def _form_highlights(side: str, team: str, last5: FormWindow, venue_last5: FormWindow) -> list[Highlight]:
    venue_word = "evde" if side == "home" else "deplasmanda"
    venue = form_statement(team, venue_last5, venue_word)
    overall = form_statement(team, last5, None)
    chosen = [s for s in (venue, overall) if s]
    if not chosen:
        return []
    chosen.sort(key=lambda s: -s[1])
    first = chosen[0]
    picked = [("form_venue" if first is venue else "form_last5", first)]
    # the second statement only when it tells the opposite story (e.g. strong overall, poor at home)
    for other in chosen[1:]:
        if other[0] != first[0]:
            picked.append(("form_venue" if other is venue else "form_last5", other))
    return [_h(kind, side, text, importance, polarity=polarity, **facts) for kind, (polarity, importance, text, facts) in picked]


# ----------------------------------------------------------------------------- goals / xG


def _goal_highlight(side: str, team: str, w: FormWindow) -> Optional[Highlight]:
    if w.played != 5 or w.goals_for is None or w.goals_against is None:
        return None
    gf, ga = w.goals_for, w.goals_against
    options: list[Highlight] = []
    if ga <= GOALS_AGAINST_LOW:
        text = f"{team} son 5 maçta kalesinde gol görmedi." if ga == 0 else f"{team} son 5 maçta sadece {ga} gol yedi."
        options.append(_h("goals_against", side, text, {0: 68, 1: 64}.get(ga, 58), goals_against=ga, played=5))
    elif ga >= GOALS_AGAINST_HIGH:
        options.append(_h("goals_against", side, f"{team} son 5 maçta {ga} gol yedi.", min(62, 56 + (ga - GOALS_AGAINST_HIGH)), goals_against=ga, played=5))
    if gf <= GOALS_FOR_LOW:
        text = f"{team} son 5 maçta gol atamadı." if gf == 0 else f"{team} son 5 maçta sadece {gf} gol attı."
        options.append(_h("goals_for", side, text, {0: 68, 1: 62}.get(gf, 56), goals_for=gf, played=5))
    elif gf >= GOALS_FOR_HIGH:
        options.append(_h("goals_for", side, f"{team} son 5 maçta {gf} gol attı.", min(62, 58 + (gf - GOALS_FOR_HIGH)), goals_for=gf, played=5))
    return max(options, key=lambda h: h.importance) if options else None


def _xg_highlight(side: str, team: str, w: FormWindow) -> Optional[Highlight]:
    """Goals against the xG of the same matches (only matches that have xG)."""
    if w.xg_matches < XG_MIN_MATCHES or w.xg_for is None or w.xg_against is None:
        return None
    with_xg = [m for m in w.matches if m.xg_for is not None and m.xg_against is not None]
    goals_for = sum(m.goals_for or 0 for m in with_xg)
    goals_against = sum(m.goals_against or 0 for m in with_xg)
    attack_gap = goals_for - w.xg_for
    defence_gap = w.xg_against - goals_against
    n = w.xg_matches
    options: list[tuple[float, Highlight]] = []
    if abs(attack_gap) >= XG_GAP:
        options.append(
            (
                abs(attack_gap),
                _h("xg_attack", side, f"{team} son {n} maçta xG toplamı {decimal(w.xg_for)} iken {goals_for} gol attı.", 52,
                   xg_for=w.xg_for, goals_for=goals_for, xg_matches=n),
            )
        )
    if abs(defence_gap) >= XG_GAP:
        options.append(
            (
                abs(defence_gap),
                _h("xg_defence", side, f"{team} son {n} maçta rakiplerin xG toplamı {decimal(w.xg_against)} iken {goals_against} gol yedi.", 52,
                   xg_against=w.xg_against, goals_against=goals_against, xg_matches=n),
            )
        )
    return max(options, key=lambda o: o[0])[1] if options else None


# ----------------------------------------------------------------------------- rest / load


def _rest_highlight(home: PreviewSide, away: PreviewSide) -> Optional[Highlight]:
    home_rest = home.rest.rest_days if home.history_verified else None
    away_rest = away.rest.rest_days if away.history_verified else None
    h_name, a_name = home.team_name or "Ev sahibi", away.team_name or "Deplasman"
    if home_rest is not None and away_rest is not None:
        short = min(home_rest, away_rest)
        gap = abs(home_rest - away_rest)
        if short > REST_SHORT_DAYS and gap < REST_GAP_DAYS:
            return None
        importance = 55 + (10 if short <= REST_SHORT_DAYS else 0) + (8 if short <= 2 else 0) + (5 if gap >= REST_GAP_DAYS else 0)
        text = (
            f"{h_name} ve {a_name} {home_rest} gün dinlendi."
            if home_rest == away_rest
            else f"{h_name} {home_rest} gün dinlendi, {a_name} {away_rest} gün."
        )
        return _h("rest", "both", text, importance, home_rest_days=home_rest, away_rest_days=away_rest)
    for side, name, rest in (("home", h_name, home_rest), ("away", a_name, away_rest)):
        if rest is not None and rest <= REST_SHORT_DAYS:
            return _h("rest", side, f"{name} {rest} gün dinlendi.", 65 + (8 if rest <= 2 else 0), rest_days=rest)
    return None


def _congestion_highlight(side: str, side_data: PreviewSide) -> Optional[Highlight]:
    n = side_data.rest.matches_last_14_days if side_data.history_verified else None
    if n is None or n < CONGESTION_MATCHES:
        return None
    team = side_data.team_name or ("Ev sahibi" if side == "home" else "Deplasman")
    return _h("congestion", side, f"{team} son 14 günde {n} maç oynadı.", 48 + 4 * min(n - CONGESTION_MATCHES, 3), matches_last_14_days=n)


# ----------------------------------------------------------------------------- absentees / rotation


def _absentee_label(player) -> Optional[str]:
    if not player.name:
        return None
    code = (player.reason_code or "").lower()
    if code == "suspension":
        return f"{player.name} (cezalı)"
    if code in ("international_duty", "internationalduty"):
        return f"{player.name} (milli takım)"
    return player.name


def _absentee_highlights(side: str, team: str, info: AbsenteesInfo) -> list[Highlight]:
    if not info.available:
        return []
    out: list[Highlight] = []
    definite = [p for p in info.players if (p.reason_code or "").lower() != "doubtful"]
    doubtful = [p for p in info.players if (p.reason_code or "").lower() == "doubtful"]
    if definite:
        # players who started the previous match first, then suspensions, then the rest (source order kept)
        definite = sorted(
            definite,
            key=lambda p: (p.started_previous_match is not True, (p.reason_code or "").lower() != "suspension"),
        )
        count = len(definite)
        labels = [x for x in (_absentee_label(p) for p in definite) if x]
        key_count = sum(1 for p in definite if p.started_previous_match)
        importance = min(92, 50 + 6 * min(count, 5) + 5 * min(key_count, 3))
        if count <= ABSENTEE_NAMES_SHOWN and len(labels) == count:
            text = f"{team} için eksikler: {join_names(labels)}."
        elif labels:
            shown = labels[:3]
            text = f"{team} için {count} oyuncu eksik: {', '.join(shown)} ve {count - len(shown)} oyuncu daha."
        else:
            text = f"{team} için {count} oyuncu eksik."
        out.append(_h("absentees", side, text, importance, count=count, started_previous_match=key_count))
    if doubtful:
        labels = [p.name for p in doubtful if p.name]
        if labels:
            out.append(_h("doubtful", side, f"{team} için şüpheli: {join_names(labels[:ABSENTEE_NAMES_SHOWN])}.", 40 + 3 * min(len(labels), 4), count=len(labels)))
    return out


def _rotation_highlight(side: str, team: str, side_data: PreviewSide) -> Optional[Highlight]:
    rotation = side_data.lineup.rotation
    lineup_type = side_data.lineup.lineup_type
    if rotation.changes is None or lineup_type not in ("confirmed", "predicted") or rotation.changes < ROTATION_CHANGES:
        return None
    n = rotation.changes
    importance = min(86, 66 + 5 * (n - ROTATION_CHANGES))
    if lineup_type == "confirmed":
        return _h("rotation", side, f"{team} geçen maça göre {n} değişiklikle sahada.", importance, changes=n, lineup_type=lineup_type)
    return _h("rotation", side, f"{team} tahmini ilk 11'de geçen maça göre {n} değişiklik var.", importance - 10, changes=n, lineup_type=lineup_type)


# ----------------------------------------------------------------------------- entry point


def build_highlights(home: PreviewSide, away: PreviewSide) -> list[Highlight]:
    """The highlights of the preview, most important first (at most MAX_HIGHLIGHTS)."""
    candidates: list[Highlight] = []
    for side, data in (("home", home), ("away", away)):
        team = data.team_name or ("Ev sahibi" if side == "home" else "Deplasman")
        if data.history_verified:
            candidates.extend(_form_highlights(side, team, data.last5, data.venue_last5))
            for fn in (_goal_highlight, _xg_highlight):
                item = fn(side, team, data.last5)
                if item:
                    candidates.append(item)
            congestion = _congestion_highlight(side, data)
            if congestion:
                candidates.append(congestion)
        candidates.extend(_absentee_highlights(side, team, data.absentees))
        rotation = _rotation_highlight(side, team, data)
        if rotation:
            candidates.append(rotation)
    rest = _rest_highlight(home, away)
    if rest:
        candidates.append(rest)
    # a goals-for / goals-against sentence and an xG sentence about the same team say nearly the same:
    # keep the stronger one per team
    candidates = _one_goal_story_per_team(candidates)
    candidates.sort(key=_sorted_key)
    out: list[Highlight] = []
    per_side = {"home": 0, "away": 0}
    for h in candidates:
        if h.side in per_side:
            if per_side[h.side] >= MAX_PER_SIDE:
                continue
            per_side[h.side] += 1
        out.append(h)
        if len(out) >= MAX_HIGHLIGHTS:
            break
    return out


def _one_goal_story_per_team(items: list[Highlight]) -> list[Highlight]:
    goal_kinds = {"goals_for", "goals_against", "xg_attack", "xg_defence"}
    best: dict[str, Highlight] = {}
    for h in items:
        if h.kind in goal_kinds and (h.side not in best or h.importance > best[h.side].importance):
            best[h.side] = h
    return [h for h in items if h.kind not in goal_kinds or best.get(h.side) is h]
