"""Collect ClubElo ratings (cross-league strength prior) and map clubs to our DB.

Source: ClubElo (Lars Schiefler), http://clubelo.com. Free, public; we keep
request volume low (1 ranking page, 1 fixtures page, ~100 club pages) and cache.

Network note (2026-10-13): the CSV API host api.clubelo.com is unreachable from
this machine (TCP timeout), and the website's dated pages (/YYYY-MM-DD) redirect
to the homepage. What *is* reachable is the website itself:
  - /Ranking           every rated club, current Elo (integer) + Golo, country
  - <homepage/Fixtures> upcoming games with ClubElo's own 1/X/2 probabilities
  - /<ClubSlug>        the club's full weekly Elo history (float) embedded as chart data
So instead of ~66 dated API snapshots we store (a) one full snapshot for today
from /Ranking and (b) weekly per-club histories for a selected set of clubs.

Outputs (backend/data/external/):
  clubelo_snapshots.csv          date, club, club_slug, country, level, elo, golo, db_team_id, source
  clubelo_ucl_2026-10-13.csv     the 9 UCL fixtures: Elo, raw Elo expectation, ClubElo 1/X/2, implied HFA
  team_name_map.csv / team_name_unmapped.csv  rows with source=clubelo

Usage (from backend/, after collect_football_data.py so country pools exist):
  venv/Scripts/python.exe -I scripts/data_collection/collect_clubelo.py
  venv/Scripts/python.exe -I scripts/data_collection/collect_clubelo.py --countries ENG,ESP,GER,ITA,FRA,TUR,POR,NED
"""
from __future__ import annotations

import argparse
import csv
import html as htmllib
import json
import math
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from external_common import (  # noqa: E402
    EXTERNAL_DIR,
    RAW_DIR,
    db_connect,
    http_get,
    is_youth_or_women,
    load_db_teams,
    name_similarity,
    normalise_name,
    read_team_map,
    write_team_map,
)

SOURCE = "clubelo"
BASE = "https://clubelo.com"
CE_RAW = RAW_DIR / "clubelo"
OUT_SNAPSHOTS = EXTERNAL_DIR / "clubelo_snapshots.csv"
FD_MATCHES = EXTERNAL_DIR / "football_data_matches.csv"
HISTORY_FROM = date(2025, 7, 1)

DEFAULT_COUNTRIES = "ENG,ESP,GER,ITA,FRA,TUR"

# The 9 UCL fixtures of 2026-10-13 requested by the team: (home slug, away slug)
UCL_FIXTURES = [
    ("Lens", "Sporting"), ("sabah-fk", "SlaviaPraha"), ("Arsenal", "Lille"), ("atletico", "ManUnited"),
    ("Galatasaray", "Barcelona"), ("Inter", "Brugge"), ("RBLeipzig", "PSV"), ("Viking", "Bayern"),
    ("Villarreal", "Napoli"),
]

# ClubElo short name -> other names to try (FotMob / common). Only used inside
# the club's country pool, and still subject to the similarity threshold.
ALIASES = {
    "Atletico": ["Atletico Madrid"], "Atlético": ["Atletico Madrid"], "Bilbao": ["Athletic Club", "Athletic Bilbao"],
    "Sociedad": ["Real Sociedad"], "Betis": ["Real Betis"], "Celta": ["Celta Vigo"], "Oviedo": ["Real Oviedo"],
    "Rayo Vallecano": ["Rayo Vallecano"], "Milan": ["AC Milan"], "Verona": ["Hellas Verona"],
    "Paris SG": ["Paris Saint-Germain"], "Paris FC": ["Paris FC"], "Bayern": ["Bayern München", "Bayern Munich"],
    "Bayern München": ["Bayern Munich"], "Gladbach": ["Borussia Monchengladbach", "Borussia M.Gladbach"],
    "Frankfurt": ["Eintracht Frankfurt"], "Koeln": ["Köln", "FC Koln"], "Köln": ["FC Koln"],
    "Forest": ["Nottingham Forest"], "Man United": ["Manchester United"], "Man City": ["Manchester City"],
    "Brugge": ["Club Brugge"], "Sporting": ["Sporting CP"], "Slavia Praha": ["Slavia Prague"],
    "PSV": ["PSV Eindhoven"], "Sabah FK": ["Sabah"], "Internazionale": ["Inter"], "Inter": ["Inter"],
    "Wolves": ["Wolverhampton Wanderers", "Wolverhampton"], "Spurs": ["Tottenham Hotspur", "Tottenham"],
    "Leverkusen": ["Bayer Leverkusen"], "Dortmund": ["Borussia Dortmund"], "Mainz": ["Mainz 05"],
    "Hoffenheim": ["TSG Hoffenheim"], "Heidenheim": ["1. FC Heidenheim"], "Stuttgart": ["VfB Stuttgart"],
    "Werder": ["Werder Bremen"], "Hamburg": ["Hamburger SV"], "St Pauli": ["St. Pauli"],
    "Union Berlin": ["1. FC Union Berlin"], "Fenerbahce": ["Fenerbahçe"], "Besiktas": ["Beşiktaş"],
    "Istanbulspor": ["İstanbulspor"], "Basaksehir": ["Başakşehir", "Istanbul Basaksehir"],
}

COUNTRY_TO_DIVS = {
    "ENG": ["E0", "E1", "E2", "E3", "EC"], "SCO": ["SC0", "SC1", "SC2", "SC3"], "GER": ["D1", "D2"],
    "ITA": ["I1", "I2"], "ESP": ["SP1", "SP2"], "FRA": ["F1", "F2"], "NED": ["N1"], "BEL": ["B1"], "POR": ["P1"],
    "TUR": ["T1"], "GRE": ["G1"], "AUT": ["AUT"], "DEN": ["DNK"], "FIN": ["FIN"], "IRL": ["IRL"], "NOR": ["NOR"],
    "POL": ["POL"], "ROU": ["ROU"], "RUS": ["RUS"], "SWE": ["SWE"], "SUI": ["SWZ"],
}


# ---------------------------------------------------------------------------
# Fetch (cached per day)
# ---------------------------------------------------------------------------


def fetch_page(path: str, cache_name: str, refresh: bool) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache = CE_RAW / f"{cache_name}_{stamp}.html"
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8", errors="replace")
    body = http_get(f"{BASE}{path}", timeout=60)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return body.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

_SIDEBAR_CLUB = re.compile(
    r'alt="([A-Z]{3})".{0,400}?<a href="/([^"]+)"><span class="NonAst">[^<]*</span><span class="Ast">([^<]*)</span></a></td><td class="r">(\d+)',
    re.S)
_ELODATA_ROW = re.compile(
    r"\['<td class=\"l\"><a href=\"/([A-Z]{3})\">[^\]]*?<a href=\"/([^\"]+)\">([^<]*)<span[^\]]*?</a></td>', '([-+]?[\d.]+)', '([-+]?[\d.]+)', '([-+]?[\d.]+)'\]",
    re.S)


def parse_ranking(page: str) -> dict[str, dict]:
    """slug -> {name, country, elo, golo, level}. Level from the per-country sidebar."""
    clubs: dict[str, dict] = {}
    for country, slug, name, elo, _chg, golo in _ELODATA_ROW.findall(page):
        clubs[slug] = {"slug": slug, "name": htmllib.unescape(name).strip(), "country": country,
                       "elo": float(elo), "golo": float(golo), "level": None}
    # Sidebar tables: '<i> Level N (k teams)</i>' headers followed by club rows (proper UTF-8 names)
    for table in re.findall(r'<table class="ast">(.*?)</table>', page, re.S):
        level = None
        for part in re.split(r"(<i>\s*Level \d+)", table):
            m = re.match(r"<i>\s*Level (\d+)", part)
            if m:
                level = int(m.group(1))
                continue
            for country, slug, name, elo in _SIDEBAR_CLUB.findall(part):
                c = clubs.setdefault(slug, {"slug": slug, "name": htmllib.unescape(name).strip(), "country": country,
                                            "elo": float(elo), "golo": None, "level": None})
                c["level"] = level
                if "�" in c["name"]:
                    c["name"] = htmllib.unescape(name).strip()
    return clubs


def parse_fixtures(page: str) -> list[dict]:
    """Games with ClubElo's published 1/X/2 probabilities (percent)."""
    games = []
    parts = re.split(r'data-live-status-game-id="(\d+)"', page)
    for i in range(1, len(parts), 2):
        gid, seg = parts[i], parts[i + 1]
        slugs = re.findall(r'<a href="/([^"]+)"><span class="max640">', seg)
        nums = [float(x) for x in re.findall(r'<span class="min1081">(-?[\d.]+)</span>', seg)]
        utc = re.search(r'data-utc-time="([^"]+)"', seg)
        if len(slugs) < 2 or len(nums) < 7:
            continue
        p1, px, p2 = nums[0], nums[1], nums[6]
        if abs(p1 + px + p2 - 100.0) > 0.6:  # layout changed -> do not trust
            continue
        games.append({"game_id": gid, "utc": utc.group(1) if utc else "", "home_slug": slugs[0],
                      "away_slug": slugs[1], "p1": p1, "px": px, "p2": p2})
    return games


def parse_history(page: str) -> list[dict]:
    pts = re.findall(r'"Date":\s*"(\d{4}-\d{2}-\d{2})T[^"]*",\s*"Elo":\s*(-?[\d.]+),\s*"Golo":\s*(-?[\d.]+|null)', page)
    seen, out = set(), []
    for d, elo, golo in pts:
        if d in seen:
            continue
        seen.add(d)
        out.append({"date": d, "elo": float(elo), "golo": None if golo == "null" else float(golo)})
    return out


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def country_pools(teams: dict[str, tuple[str, str]]) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Country -> DB team ids that play in that country's league competitions.

    League competitions are taken from football_data_matches.csv rows that were
    linked to a DB match (so they are verified by result), per country.
    """
    comp_by_country: dict[str, set[str]] = defaultdict(set)
    if FD_MATCHES.exists():
        with FD_MATCHES.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r["db_match_id"] and r["db_competition_provider_id"]:
                    comp_by_country[r["country"]].add(r["db_competition_provider_id"])
    pools: dict[str, set[str]] = defaultdict(set)
    if comp_by_country:
        con = db_connect()
        comp_pid = {cid: pid for cid, pid in con.execute("select id, provider_id from competitions")}
        for comp_id, h, a in con.execute("select competition_id, home_team_id, away_team_id from matches"):
            pid = comp_pid.get(comp_id)
            for country, pids in comp_by_country.items():
                if pid in pids:
                    pools[country].update((h, a))
        con.close()
    # extra name variants: football-data names already verified by fixtures
    variants: dict[str, list[str]] = defaultdict(list)
    for r in read_team_map("football_data"):
        variants[r["db_team_id"]].append(r["source_name"])
    return pools, variants


def match_club(name: str, country: str, pools, variants, teams, global_index) -> dict:
    tries = [name] + ALIASES.get(name, [])
    if is_youth_or_women(name):
        return {"ok": False, "reason": "reserve/youth/women side: not mapped automatically"}
    pool = pools.get(country)
    if pool:
        scored: dict[str, float] = {}
        for tid in pool:
            tname = teams[tid][0]
            if is_youth_or_women(tname):
                continue
            best = 0.0
            for cand in [tname] + variants.get(tid, []):
                for t in tries:
                    best = max(best, name_similarity(t, cand))
            scored[tid] = best
        ranked = sorted(scored.items(), key=lambda kv: -kv[1])
        if not ranked:
            return {"ok": False, "reason": "empty country pool"}
        (tid, s1) = ranked[0]
        s2 = ranked[1][1] if len(ranked) > 1 else 0.0
        if s1 >= 0.86 and (s1 - s2) >= 0.08:
            method = "name_exact_in_country_pool" if s1 >= 0.999 else "name_fuzzy_in_country_pool"
            return {"ok": True, "id": tid, "method": method, "confidence": round(s1, 3),
                    "evidence": f"country pool {country} ({len(pool)} teams); runner-up sim {s2:.2f}"}
        pool_fail = {"ok": False, "candidate": tid, "score": round(s1, 3),
                     "reason": f"ambiguous/low similarity in country pool (best {s1:.2f}, runner-up {s2:.2f})"}
        if s1 >= 0.86:  # a near-tie inside the pool: do not fall back to a global search
            return pool_fail
    else:
        pool_fail = None
    # No pool: exact normalised name, unique across all senior DB teams.
    hits = set()
    for t in tries:
        hits |= global_index.get(normalise_name(t), set())
    if len(hits) == 1 and not (pool and next(iter(hits)) in pool):
        tid = next(iter(hits))
        why = "not found in country pool" if pool else f"no country pool for {country}"
        return {"ok": True, "id": tid, "method": "name_exact_global_unique", "confidence": 0.8,
                "evidence": f"{why}; unique exact normalised name among all senior DB teams"}
    if pool_fail:
        return pool_fail
    return {"ok": False, "candidate": next(iter(hits)) if hits else None, "score": "",
            "reason": f"no country pool for {country} and {len(hits)} exact global name hits"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def elo_expectation(d_elo: float) -> float:
    """ClubElo/Elo equation: expected score (win + 0.5*draw) for rating difference d_elo."""
    return 1.0 / (10 ** (-d_elo / 400.0) + 1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default=DEFAULT_COUNTRIES, help="level-1 clubs of these countries get histories")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--refresh", action="store_true", help="re-fetch today's ranking/fixtures pages")
    ap.add_argument("--max-clubs", type=int, default=150)
    args = ap.parse_args()

    ranking = parse_ranking(fetch_page("/Ranking", "ranking", args.refresh))
    print(f"ranking clubs parsed: {len(ranking)} (with level: {sum(1 for c in ranking.values() if c['level'])})")
    games = parse_fixtures(fetch_page("/", "home", args.refresh))
    try:
        games += parse_fixtures(fetch_page("/Fixtures", "fixtures", args.refresh))
    except Exception as exc:
        print(f"fixtures page unavailable: {exc!r}")
    by_pair = {}
    for g in games:
        by_pair.setdefault((g["home_slug"].lower(), g["away_slug"].lower()), g)
    print(f"fixtures parsed: {len(by_pair)}")

    # Clubs that get a weekly history
    countries = {c.strip().upper() for c in args.countries.split(",") if c.strip()}
    slug_lc = {s.lower(): s for s in ranking}
    wanted: list[str] = []
    for h, a in UCL_FIXTURES:
        for s in (h, a):
            real = slug_lc.get(s.lower(), s)
            if real not in wanted:
                wanted.append(real)
    for slug, c in sorted(ranking.items(), key=lambda kv: -kv[1]["elo"]):
        if c["country"] in countries and c["level"] == 1 and slug not in wanted:
            wanted.append(slug)
    wanted = wanted[: args.max_clubs]

    hist_dir = CE_RAW / "club_history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    histories: dict[str, list[dict]] = {}
    failures = []
    for slug in wanted:
        cache = hist_dir / f"{slug}.json"
        if cache.exists():
            histories[slug] = json.loads(cache.read_text(encoding="utf-8"))["points"]
            continue
        try:
            page = http_get(f"{BASE}/{slug}", timeout=60).decode("utf-8", errors="replace")
            pts = parse_history(page)
            if not pts:
                raise ValueError("no history points found in page")
            cache.write_text(json.dumps({"slug": slug, "fetched_at": datetime.now(timezone.utc).isoformat(),
                                         "points": pts}), encoding="utf-8")
            histories[slug] = pts
            print(f"[ok] history {slug}: {len(pts)} points, last {pts[-1]['date']}")
        except Exception as exc:
            failures.append((slug, repr(exc)))
            print(f"[fail] history {slug}: {exc!r}")
        time.sleep(args.delay)

    # Map every ranked club to the DB
    con = db_connect()
    teams = load_db_teams(con)
    con.close()
    pools, variants = country_pools(teams)
    global_index: dict[str, set[str]] = defaultdict(set)
    for tid, (tname, _pid) in teams.items():
        if not is_youth_or_women(tname):
            global_index[normalise_name(tname)].add(tid)
    mapped, unmapped, slug_to_db = [], [], {}
    results = {slug: match_club(c["name"], c["country"], pools, variants, teams, global_index)
               for slug, c in ranking.items()}
    # One DB team may be claimed by one club only; on a conflict keep a strictly
    # better-scored claim, otherwise unmap every claimant.
    claims = defaultdict(list)
    for slug, res in results.items():
        if res["ok"]:
            claims[res["id"]].append(slug)
    for tid, slugs in claims.items():
        if len(slugs) < 2:
            continue
        ranked = sorted(slugs, key=lambda s: -results[s]["confidence"])
        keep = ranked[0] if results[ranked[0]]["confidence"] > results[ranked[1]]["confidence"] else None
        for s in slugs:
            if s != keep:
                results[s] = {"ok": False, "candidate": tid, "score": results[s]["confidence"],
                              "reason": f"DB team also claimed by {len(slugs) - 1} other ClubElo club(s)"}
    for slug, c in sorted(ranking.items()):
        res = results[slug]
        ctx = f"{c['country']} level {c['level'] if c['level'] else 'unknown'} (slug {slug})"
        if res["ok"]:
            tid = res["id"]
            slug_to_db[slug] = tid
            mapped.append({"source": SOURCE, "source_name": c["name"], "source_context": ctx, "db_team_id": tid,
                           "db_team_provider_id": teams[tid][1], "db_team_name": teams[tid][0],
                           "method": res["method"], "confidence": res["confidence"], "evidence": res["evidence"]})
        else:
            cand = res.get("candidate")
            unmapped.append({"source": SOURCE, "source_name": c["name"], "source_context": ctx,
                             "best_candidate_db_team_name": teams[cand][0] if cand else "",
                             "best_candidate_score": res.get("score", ""), "reason": res["reason"]})
    write_team_map(SOURCE, mapped, unmapped)

    # Snapshots table
    today = datetime.now(timezone.utc).date().isoformat()
    n_rows = 0
    with OUT_SNAPSHOTS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "club", "club_slug", "country", "level", "elo", "golo",
                                          "db_team_id", "source"])
        w.writeheader()
        for slug, pts in sorted(histories.items()):
            c = ranking.get(slug, {"name": slug, "country": "", "level": None})
            for p in pts:
                if p["date"] < HISTORY_FROM.isoformat():
                    continue
                w.writerow({"date": p["date"], "club": c["name"], "club_slug": slug, "country": c["country"],
                            "level": c["level"] or "", "elo": round(p["elo"], 2),
                            "golo": "" if p["golo"] is None else p["golo"], "db_team_id": slug_to_db.get(slug, ""),
                            "source": "club_history_weekly"})
                n_rows += 1
        for slug, c in sorted(ranking.items()):
            w.writerow({"date": today, "club": c["name"], "club_slug": slug, "country": c["country"],
                        "level": c["level"] or "", "elo": c["elo"], "golo": "" if c["golo"] is None else c["golo"],
                        "db_team_id": slug_to_db.get(slug, ""), "source": "ranking_page_current"})
            n_rows += 1

    # UCL fixtures table
    ucl_rows = []
    for h, a in UCL_FIXTURES:
        hs, as_ = slug_lc.get(h.lower(), h), slug_lc.get(a.lower(), a)
        ch, ca = ranking.get(hs), ranking.get(as_)
        hh, ha = histories.get(hs), histories.get(as_)
        row = {"home": ch["name"] if ch else hs, "away": ca["name"] if ca else as_,
               "home_db_team_id": slug_to_db.get(hs, ""), "away_db_team_id": slug_to_db.get(as_, ""),
               "home_db_team_name": teams[slug_to_db[hs]][0] if hs in slug_to_db else "",
               "away_db_team_name": teams[slug_to_db[as_]][0] if as_ in slug_to_db else "",
               "home_elo": round(hh[-1]["elo"], 1) if hh else (ch["elo"] if ch else ""),
               "home_elo_date": hh[-1]["date"] if hh else (today if ch else ""),
               "away_elo": round(ha[-1]["elo"], 1) if ha else (ca["elo"] if ca else ""),
               "away_elo_date": ha[-1]["date"] if ha else (today if ca else "")}
        if row["home_elo"] != "" and row["away_elo"] != "":
            d = float(row["home_elo"]) - float(row["away_elo"])
            row["elo_diff"] = round(d, 1)
            row["expected_score_home_no_hfa"] = round(elo_expectation(d), 4)
        g = by_pair.get((hs.lower(), as_.lower()))
        if g:
            row.update({"clubelo_p_home": g["p1"], "clubelo_p_draw": g["px"], "clubelo_p_away": g["p2"],
                        "clubelo_kickoff_utc": g["utc"]})
            e_ce = (g["p1"] + 0.5 * g["px"]) / 100.0
            row["clubelo_expected_score_home"] = round(e_ce, 4)
            if "elo_diff" in row and 0 < e_ce < 1:
                dr = -400.0 * math.log10(1.0 / e_ce - 1.0)
                row["implied_dr_with_hfa"] = round(dr, 1)
                row["implied_hfa_points"] = round(dr - row["elo_diff"], 1)
        ucl_rows.append(row)
    ucl_path = EXTERNAL_DIR / "clubelo_ucl_2026-10-13.csv"
    fields = ["home", "away", "home_db_team_id", "home_db_team_name", "away_db_team_id", "away_db_team_name",
              "home_elo", "home_elo_date", "away_elo", "away_elo_date", "elo_diff", "expected_score_home_no_hfa",
              "clubelo_p_home", "clubelo_p_draw", "clubelo_p_away", "clubelo_expected_score_home",
              "implied_dr_with_hfa", "implied_hfa_points", "clubelo_kickoff_utc"]
    with ucl_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ucl_rows:
            w.writerow({k: r.get(k, "") for k in fields})

    print(f"histories: {len(histories)} clubs, failures: {len(failures)}")
    print(f"snapshot rows written: {n_rows} -> {OUT_SNAPSHOTS}")
    print(f"clubelo clubs mapped: {len(mapped)} / {len(ranking)}  (unmapped {len(unmapped)})")
    by_c = defaultdict(lambda: [0, 0])
    for r in mapped:
        by_c[r["source_context"][:3]][0] += 1
    for r in unmapped:
        by_c[r["source_context"][:3]][1] += 1
    print("mapped/unmapped by country (top):",
          sorted(((k, v[0], v[1]) for k, v in by_c.items()), key=lambda x: -(x[1] + x[2]))[:25])
    for r in ucl_rows:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
