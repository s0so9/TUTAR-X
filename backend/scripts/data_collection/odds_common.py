"""Shared helpers for the bookmaker-odds collectors (research prototypes, 2026-10-15).

NOT wired into the app or the model. Used by ``collect_odds_fotmob.py`` and
``collect_odds_oddsapiio.py``. No new dependency (stdlib + httpx, which the other collectors use).

What lives here
  * odds validation (``parse_decimal_odds``): a price is a finite decimal number > 1.0, anything else is
    ``None`` - a missing or broken price is never turned into 0 or a guess (AGENTS.md rule 14)
  * margin removal: ``devig_proportional`` and ``devig_shin`` (Shin 1993, solved as in Strumbelj 2014;
    the same maths as ``scripts/research/xdata_devig.py``, in pure Python)
  * canonical markets (``build_market``): 1x2, double_chance, btts, ou_1.5 / ou_2.5 / ou_3.5, with
    overround and de-vigged probabilities; markets that fail sanity checks are rejected, not repaired
  * fixture handling: ``Fixture``, ``parse_fotmob_matches_payload`` / ``fetch_fotmob_fixtures``
    (FotMob day list through the shared limiter ``fotmob_rate``) and ``map_events_to_fixtures``
    (team names + kick-off, with a confidence; unmapped fixtures are listed with the reason, never guessed)
  * ``redact`` (API keys in URLs/exceptions) and ``append_jsonl``

Odds are bookmaker prices as delivered by the source (real data when a real source is used). Test fixtures
in ``backend/tests/test_collect_odds_*.py`` are SYNTHETIC and labelled as such.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ODDS_DIR = BACKEND_DIR / "data" / "odds"

FOTMOB_BASE_URL = "https://www.fotmob.com"
FOTMOB_HEADERS = {"User-Agent": "Mozilla/5.0 (TUTAR X research collector; low-rate)", "Accept": "application/json"}

# FotMob league ids of the project's target competitions (10 leagues + UCL / UEL / UECL), same as
# collect_fotmob_details.TARGET13.
TARGET13 = [47, 87, 55, 54, 53, 57, 61, 40, 71, 122, 42, 73, 10216]

# canonical markets -> ordered outcome names
MARKETS: dict[str, tuple[str, ...]] = {
    "1x2": ("home", "draw", "away"),
    "double_chance": ("1x", "12", "x2"),
    "btts": ("yes", "no"),
    "ou_1.5": ("over", "under"),
    "ou_2.5": ("over", "under"),
    "ou_3.5": ("over", "under"),
}
OU_LINES = (1.5, 2.5, 3.5)

# overround (sum of 1/odds) outside this range means a wrong parse or a broken price: market rejected
OVERROUND_MIN = 0.99
OVERROUND_MAX = 1.40


# --------------------------------------------------------------------------------------------------
# odds validation and margin removal
# --------------------------------------------------------------------------------------------------
def parse_decimal_odds(value: Any) -> Optional[float]:
    """Decimal odds as float, or ``None`` when the value is missing, not numeric, not finite or <= 1.0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        x = float(str(value).strip().replace(",", ".")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x <= 1.0:
        return None
    return x


def overround(odds: Iterable[float]) -> float:
    """Sum of implied probabilities 1/odds."""
    return sum(1.0 / o for o in odds)


def devig_proportional(odds: list[float], target: float = 1.0) -> list[float]:
    """p_i = target * (1/o_i) / sum_j (1/o_j). ``target`` is 1 for exclusive outcomes and 2 for double chance."""
    q = [1.0 / o for o in odds]
    s = sum(q)
    return [target * x / s for x in q]


def devig_shin(odds: list[float]) -> tuple[list[float], float]:
    """Shin (1993) insider model: p_i(z) = (sqrt(z^2 + 4(1-z) q_i^2 / B) - z) / (2(1-z)), q_i = 1/o_i, B = sum q,
    with the insider share z solving sum_i p_i(z) = 1 (bisection). Returns (probabilities, z).
    Without margin (B <= 1) the proportional probabilities and z = 0 are returned."""
    q = [1.0 / o for o in odds]
    big_b = sum(q)
    if big_b <= 1.0:
        return [x / big_b for x in q], 0.0

    def p_of(z: float) -> list[float]:
        return [(math.sqrt(z * z + 4.0 * (1.0 - z) * x * x / big_b) - z) / (2.0 * (1.0 - z)) for x in q]

    def f(z: float) -> float:
        return sum(p_of(z)) - 1.0

    lo, hi = 0.0, 0.5
    while f(hi) > 0.0 and hi < 0.999:
        hi = min(0.999, hi + (1.0 - hi) / 2.0)
    if f(lo) <= 0.0 or f(hi) > 0.0:  # no sign change: cannot solve, fall back to proportional
        return [x / big_b for x in q], float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if f(mid) > 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-14:
            break
    z = (lo + hi) / 2.0
    p = p_of(z)
    s = sum(p)
    return [x / s for x in p], z


def build_market(name: str, odds: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Canonical market record from raw prices, or ``None`` when any outcome price is missing/invalid or the
    overround is implausible (never repaired). ``name`` is a key of ``MARKETS``.

    Result: odds, overround, margin, p_proportional and p_shin (None for double chance, where the probabilities
    sum to 2 and the Shin model does not apply), shin_z.
    """
    outcomes = MARKETS[name]
    parsed = [parse_decimal_odds(odds.get(o)) for o in outcomes]
    if any(x is None for x in parsed):
        return None
    prices = [float(x) for x in parsed]  # type: ignore[arg-type]
    is_dc = name == "double_chance"
    over = overround(prices) / (2.0 if is_dc else 1.0)
    if not (OVERROUND_MIN <= over <= OVERROUND_MAX):
        return None
    rec: dict[str, Any] = {
        "odds": {o: round(p, 4) for o, p in zip(outcomes, prices)},
        "overround": round(over, 5),
        "margin": round(over - 1.0, 5),
    }
    if is_dc:
        rec["p_proportional"] = {o: round(p, 6) for o, p in zip(outcomes, devig_proportional(prices, target=2.0))}
        rec["p_shin"] = None
        rec["shin_z"] = None
        rec["devig_note"] = "double chance: the three probabilities sum to 2; Shin does not apply"
    else:
        rec["p_proportional"] = {o: round(p, 6) for o, p in zip(outcomes, devig_proportional(prices))}
        ps, z = devig_shin(prices)
        if math.isnan(z):
            rec["p_shin"] = None
            rec["shin_z"] = None
        else:
            rec["p_shin"] = {o: round(p, 6) for o, p in zip(outcomes, ps)}
            rec["shin_z"] = round(z, 6)
    return rec


def canonical_missing(markets: dict[str, Any]) -> list[str]:
    """Canonical markets that are absent from ``markets`` (explicit 'unavailable', rule 14)."""
    return [m for m in MARKETS if m not in markets]


def ou_market_name(line: Any) -> Optional[str]:
    """'ou_2.5' for 2.5 (also 2.50 / '2.5'); ``None`` for lines we do not track."""
    try:
        x = float(line)
    except (TypeError, ValueError):
        return None
    for tracked in OU_LINES:
        if abs(x - tracked) < 1e-9:
            return f"ou_{tracked}"
    return None


# --------------------------------------------------------------------------------------------------
# fixtures and team mapping
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fixture:
    match_id: str  # FotMob match id (== matches.provider_id in the local DB)
    home: str
    away: str
    kickoff: datetime  # aware, UTC
    competition_id: Optional[int] = None
    competition_name: Optional[str] = None
    home_id: Optional[int] = None
    away_id: Optional[int] = None
    started: bool = False
    finished: bool = False
    cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fotmob_match_id": self.match_id,
            "home": self.home,
            "away": self.away,
            "kickoff_utc": self.kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "competition_id": self.competition_id,
            "competition_name": self.competition_name,
        }


def parse_utc(value: Any) -> Optional[datetime]:
    """ISO-8601 string ('...Z', '+00:00', milliseconds) or epoch milliseconds -> aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_fotmob_matches_payload(payload: Any, featured_ids: Iterable[int] = TARGET13) -> list[Fixture]:
    """Fixtures of the featured competitions from a FotMob ``/api/data/matches?date=`` payload
    (``{"leagues": [{"id", "primaryId", "name", "matches": [...]}]}``). A league counts as featured when its
    ``primaryId`` (or, if absent, ``id``) is in ``featured_ids``. Matches without a parseable kick-off are skipped."""
    featured = {int(x) for x in featured_ids}
    out: list[Fixture] = []
    leagues = payload.get("leagues") if isinstance(payload, dict) else None
    for lg in leagues or []:
        primary = lg.get("primaryId", lg.get("id"))
        try:
            primary_i = int(primary)
        except (TypeError, ValueError):
            continue
        if primary_i not in featured:
            continue
        for m in lg.get("matches") or []:
            status = m.get("status") or {}
            kickoff = parse_utc(status.get("utcTime")) or parse_utc(m.get("timeTS"))
            home, away = m.get("home") or {}, m.get("away") or {}
            if kickoff is None or m.get("id") is None or not home.get("name") or not away.get("name"):
                continue
            out.append(
                Fixture(
                    match_id=str(m["id"]),
                    home=str(home["name"]),
                    away=str(away["name"]),
                    kickoff=kickoff,
                    competition_id=primary_i,
                    competition_name=lg.get("name"),
                    home_id=_int_or_none(home.get("id")),
                    away_id=_int_or_none(away.get("id")),
                    started=bool(status.get("started")),
                    finished=bool(status.get("finished")),
                    cancelled=bool(status.get("cancelled")),
                )
            )
    out.sort(key=lambda f: (f.kickoff, f.match_id))
    return out


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class FotmobBlocked(RuntimeError):
    """FotMob answered 403 or a challenge page: the run stops, nothing is worked around."""


class FotmobRateLimited(RuntimeError):
    """FotMob answered 429; the shared limiter was told to cool down."""


def fotmob_get(client: Any, path_and_query: str, *, limiter: Any = None, max_hops: int = 3) -> Any:
    """GET one FotMob JSON resource. The shared limiter ``acquire()`` runs before EVERY hop (also before the
    redirect that FotMob answers with when it picks a betting provider). 403 / non-JSON challenge pages raise
    ``FotmobBlocked``; 429 reports the cool-down to the limiter and raises ``FotmobRateLimited``.
    Returns the decoded JSON (``None`` when FotMob answers JSON ``null``)."""
    if limiter is None:
        import fotmob_rate as limiter  # noqa: PLC0415  (sibling module)
    url = path_and_query if path_and_query.startswith("http") else FOTMOB_BASE_URL + path_and_query
    resp = None
    for _ in range(max_hops):
        limiter.acquire()
        resp = client.get(url, headers=FOTMOB_HEADERS, follow_redirects=False)
        if resp.status_code in (301, 302, 307, 308) and resp.headers.get("location"):
            loc = resp.headers["location"]
            url = loc if loc.startswith("http") else FOTMOB_BASE_URL + loc
            continue
        break
    assert resp is not None
    if resp.status_code == 429:
        try:
            wait = float(resp.headers.get("retry-after", 60))
        except ValueError:
            wait = 60.0
        limiter.report_429(wait)
        raise FotmobRateLimited(f"HTTP 429 (cool-down {wait:.0f}s)")
    if resp.status_code == 403:
        raise FotmobBlocked("HTTP 403 from FotMob")
    ctype = resp.headers.get("content-type", "")
    if resp.status_code == 204:
        return None
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} for {url.split('?')[0]}")
    if "json" not in ctype:
        head = resp.text[:200].lower()
        if "captcha" in head or "challenge" in head or "just a moment" in head:
            raise FotmobBlocked("challenge page from FotMob")
        raise RuntimeError(f"non-JSON answer ({ctype or 'no content-type'}) for {url.split('?')[0]}")
    return json.loads(resp.text) if resp.text.strip() else None


def fetch_fotmob_fixtures(client: Any, date_str: str, featured_ids: Iterable[int] = TARGET13, *, limiter: Any = None) -> list[Fixture]:
    """Featured fixtures of a day (``YYYY-MM-DD``) from FotMob's day list (ONE request, same call the app makes)."""
    compact = date_str.replace("-", "")
    payload = fotmob_get(client, f"/api/data/matches?date={compact}", limiter=limiter)
    return parse_fotmob_matches_payload(payload, featured_ids)


# --- team-name matching --------------------------------------------------------------------------
_STOP_TOKENS = {
    "fc", "cf", "afc", "sc", "ac", "as", "ssc", "fk", "sk", "sv", "vfb", "vfl", "tsg", "ud", "cd", "rc",
    "club", "calcio", "de", "the", "bk", "if", "ik", "ff", "nk", "kv", "krc", "rsc", "og", "us", "ss", "fcv",
    "jk", "bsc", "fsv", "tsv", "spvgg", "kaa", "ksv", "hsc", "fcu",
}
# well-known English <-> local exonyms (generic place names, not club data); applied token by token
_EXONYMS = {"prague": "praha", "munich": "munchen", "cologne": "koln", "nuremberg": "nurnberg", "vienna": "wien",
            "moscow": "moskva", "warsaw": "warszawa", "kiev": "kyiv", "seville": "sevilla", "genoa": "genova",
            "lisbon": "lisboa", "copenhagen": "kobenhavn", "gothenburg": "goteborg", "brussels": "bruxelles"}


def normalize_team(name: str) -> str:
    """Lower-case, accents removed, punctuation -> spaces, filler tokens (fc, ac, sk, ...) and bare years dropped."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ").replace("ø", "o").replace("ł", "l").replace("đ", "d").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [_EXONYMS.get(t, t) for t in s.split() if t not in _STOP_TOKENS and not re.fullmatch(r"(18|19|20)\d\d|0\d", t)]
    return " ".join(toks)


def team_similarity(a: str, b: str) -> float:
    """1.0 for equal normalized names; 0.88 minus 0.03 per extra token when one name's tokens are a subset of
    the other's ('milan' vs 'ac milan' is equal after normalising; 'inter' vs 'inter milan' = 0.85); otherwise
    0.95 * string ratio, capped so that a non-subset pair can never reach 1.0."""
    na, nb = normalize_team(a), normalize_team(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        extra = abs(len(ta) - len(tb))
        return max(0.0, 0.88 - 0.03 * extra)
    return round(0.95 * difflib.SequenceMatcher(None, na, nb).ratio(), 4)


@dataclass
class EventLite:
    """A vendor event reduced to what the mapping needs."""

    event_id: Any
    home: str
    away: str
    kickoff: datetime
    league: Optional[str] = None


ACCEPT_MIN_CONFIDENCE = 0.80
KICKOFF_TOLERANCE = timedelta(minutes=15)


def _score(fixture: Fixture, ev: EventLite) -> tuple[float, float, float]:
    sh = team_similarity(fixture.home, ev.home)
    sa = team_similarity(fixture.away, ev.away)
    dt = abs((fixture.kickoff - ev.kickoff).total_seconds()) / 60.0
    return sh, sa, dt


def map_events_to_fixtures(
    fixtures: list[Fixture], events: list[EventLite]
) -> tuple[dict[str, tuple[EventLite, float, str]], list[dict[str, Any]]]:
    """One-to-one mapping vendor event -> our fixture, by team names and kick-off.

    A pair is accepted when kick-off differs by at most 15 minutes, both team similarities are >= 0.80 and the
    pair is the unique best for BOTH sides (no other event for the fixture and no other fixture for the event
    within 0.05 of its confidence). confidence = min(home sim, away sim), x0.95 when the kick-offs differ by more
    than 5 minutes. Everything else is returned in the unmapped list with the reason (and the best candidate
    seen) - nothing is guessed. Returns ({match_id: (event, confidence, evidence)}, unmapped).
    """
    cands: dict[str, list[tuple[float, EventLite, str]]] = {}
    for fx in fixtures:
        lst: list[tuple[float, EventLite, str]] = []
        for ev in events:
            sh, sa, dt = _score(fx, ev)
            if dt > KICKOFF_TOLERANCE.total_seconds() / 60.0:
                continue
            conf = min(sh, sa) * (1.0 if dt <= 5 else 0.95)
            lst.append((round(conf, 4), ev, f"home_sim={sh:.2f} away_sim={sa:.2f} kickoff_diff_min={dt:.0f}"))
        lst.sort(key=lambda x: -x[0])
        cands[fx.match_id] = lst

    # which fixtures could each vendor event belong to (confidence >= threshold)? used for the uniqueness check
    claims: dict[Any, list[tuple[float, str]]] = {}
    for mid, lst in cands.items():
        for conf, ev, _ in lst:
            if conf >= ACCEPT_MIN_CONFIDENCE:
                claims.setdefault(ev.event_id, []).append((conf, mid))

    mapped: dict[str, tuple[EventLite, float, str]] = {}
    unmapped: list[dict[str, Any]] = []
    for fx in fixtures:
        lst = cands[fx.match_id]
        entry = {"fotmob_match_id": fx.match_id, "home": fx.home, "away": fx.away, "kickoff_utc": fx.kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if not lst:
            unmapped.append({**entry, "reason": "no vendor event within 15 min of kick-off"})
            continue
        conf, ev, evidence = lst[0]
        best = {"event_id": ev.event_id, "home": ev.home, "away": ev.away, "confidence": conf, "evidence": evidence}
        if conf < ACCEPT_MIN_CONFIDENCE:
            # accepting a swapped pair would put the odds on the wrong side
            swapped = min(team_similarity(fx.home, ev.away), team_similarity(fx.away, ev.home))
            reason = "home/away appear swapped at the vendor" if swapped >= ACCEPT_MIN_CONFIDENCE else "best candidate below the name-similarity threshold"
            unmapped.append({**entry, "reason": reason, "best_candidate": best})
            continue
        if len(lst) > 1 and lst[1][0] >= ACCEPT_MIN_CONFIDENCE and lst[1][0] >= conf - 0.05:
            unmapped.append({**entry, "reason": "ambiguous: two vendor events match this fixture about equally", "best_candidate": best})
            continue
        rivals = [c for c, mid in claims.get(ev.event_id, []) if mid != fx.match_id]
        if rivals and max(rivals) >= conf - 0.05:
            unmapped.append({**entry, "reason": "ambiguous: the vendor event matches another fixture about equally", "best_candidate": best})
            continue
        mapped[fx.match_id] = (ev, conf, evidence)
    return mapped, unmapped


# --------------------------------------------------------------------------------------------------
# keyed vendor APIs (Odds-API.io, OddsPapi): request budget, errors, one GET helper
# --------------------------------------------------------------------------------------------------
class VendorError(RuntimeError):
    """A vendor request failed; the message never contains the API key."""


class QuotaStop(VendorError):
    """429 / request cap reached: the run stops and keeps what it has."""


class RequestBudget:
    """Counts requests, enforces a per-run cap and a minimum interval between requests (free plans are small:
    Odds-API.io 100/hour, OddsPapi 250/month with a 1 s endpoint cool-down)."""

    def __init__(self, max_requests: int = 40, min_interval: float = 0.6, sleep=time.sleep, clock=time.monotonic):
        self.max_requests, self.min_interval = max_requests, min_interval
        self.used = 0
        self.remaining_header: Optional[str] = None
        self._last = 0.0
        self._sleep, self._clock = sleep, clock

    def before(self) -> None:
        if self.used >= self.max_requests:
            raise QuotaStop(f"request cap of this run reached ({self.max_requests})")
        wait = self.min_interval - (self._clock() - self._last)
        if wait > 0 and self._last:
            self._sleep(wait)
        self.used += 1
        self._last = self._clock()


def vendor_get(client: Any, base_url: str, path: str, params: dict[str, Any], key: str, budget: RequestBudget, *, remaining_header: str = "x-ratelimit-remaining") -> Any:
    """GET ``base_url + path`` with ``apiKey=<key>`` as query parameter (both vendors' documented scheme).
    429 -> ``QuotaStop``; 401/403/other errors -> ``VendorError`` with the key redacted from every message."""
    budget.before()
    try:
        resp = client.get(base_url + path, params={**params, "apiKey": key})
    except Exception as exc:  # noqa: BLE001 - httpx errors embed the URL (and with it the key)
        raise VendorError(f"network error on {path}: {redact(exc, key)}") from None
    budget.remaining_header = resp.headers.get(remaining_header, budget.remaining_header)
    if resp.status_code == 429:
        raise QuotaStop(f"HTTP 429 on {path} (rate limit; remaining header {budget.remaining_header})")
    if resp.status_code in (401, 403):
        raise VendorError(f"HTTP {resp.status_code} on {path}: key rejected or endpoint not in the plan")
    if resp.status_code != 200:
        raise VendorError(f"HTTP {resp.status_code} on {path}: {redact(resp.text[:200], key)}")
    try:
        return resp.json()
    except ValueError:
        raise VendorError(f"non-JSON answer on {path}") from None


# --------------------------------------------------------------------------------------------------
# misc
# --------------------------------------------------------------------------------------------------
_KEY_RE = re.compile(r"(api[_-]?key=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: Any, secret: Optional[str] = None) -> str:
    """``text`` with ``apiKey=...`` query values and the literal secret removed (URLs end up in exception texts)."""
    s = _KEY_RE.sub(r"\1***", str(text))
    if secret:
        s = s.replace(secret, "***")
    return s


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Append one JSON object per line (UTF-8, no ASCII escaping). Returns the number of lines written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


def seconds_to_kickoff(kickoff: datetime, fetched_at: datetime) -> int:
    return int((kickoff - fetched_at).total_seconds())


def build_snapshot(
    *,
    fixture: Fixture,
    source: str,
    bookmaker: str,
    markets: dict[str, dict[str, Any]],
    fetched_at: datetime,
    mapping: dict[str, Any],
    region: Optional[str] = None,
    odds_updated_at: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """One output line: one bookmaker's pre-match prices for one fixture at one fetch time."""
    return {
        "schema": "odds_snapshot_v1",
        "fotmob_match_id": fixture.match_id,
        "match": fixture.to_dict(),
        "source": source,
        "bookmaker": bookmaker,
        "region": region,
        "odds_type": "pre_match",
        "fetched_at": iso_z(fetched_at),
        "odds_updated_at": odds_updated_at,
        "seconds_to_kickoff": seconds_to_kickoff(fixture.kickoff, fetched_at),
        # "closing" would need a snapshot taken right before kick-off; flagged here for the consumer to decide
        "is_closing": False,
        "mapping": mapping,
        "markets": markets,
        "missing_markets": canonical_missing(markets),
        **(extra or {}),
    }
