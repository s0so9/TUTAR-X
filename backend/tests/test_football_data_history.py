"""Unit tests for the football-data.co.uk history -> FotMob mapping (football_data_history.py).

Every team, fixture, score and odds value below is a SYNTHETIC TEST FIXTURE made up
for these tests (team names end in "(test)"). It is not football data and is never
written to any dataset; the tests touch no network, no DB and no data file.
"""

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[1] / "scripts" / "data_collection"
sys.path.insert(0, str(_DIR))
_spec = importlib.util.spec_from_file_location("football_data_history", _DIR / "football_data_history.py")
fdh = importlib.util.module_from_spec(_spec)
sys.modules["football_data_history"] = fdh  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(fdh)

# Synthetic league: football-data name -> FotMob id / FotMob name (all made up)
TEAMS = {
    "Alpha (test)": ("101", "Alpha United (test)"),
    "Beta (test)": ("102", "Beta City (test)"),
    "Gamma (test)": ("103", "Gamma Rovers (test)"),
    "Delta (test)": ("104", "Delta Athletic (test)"),
}
START = date(2022, 8, 6)


def _schedule():
    """Double round robin for 4 synthetic teams: 6 weekends, 2 matches each, distinct synthetic scores."""
    names = list(TEAMS)
    rounds = [
        [(0, 1), (2, 3)], [(0, 2), (1, 3)], [(0, 3), (1, 2)],
        [(1, 0), (3, 2)], [(2, 0), (3, 1)], [(3, 0), (2, 1)],
    ]
    out = []
    n = 0
    for k, rnd in enumerate(rounds):
        for h, a in rnd:
            n += 1
            out.append((START + timedelta(days=7 * k), names[h], names[a], n % 4, (n * 3) % 5))
    return out


def _fd_rows(schedule, day_shift=None):
    rows = []
    for i, (d, h, a, hg, ag) in enumerate(schedule):
        shift = (day_shift or {}).get(i, 0)
        rows.append(fdh.FdRow("2223", "E0", d + timedelta(days=shift), "15:00", h, a, hg, ag,
                              "H" if hg > ag else "A" if ag > hg else "D", {}))
    return rows


def _fixtures(schedule, utc_shift_days=0):
    fx = []
    for i, (d, h, a, hg, ag) in enumerate(schedule):
        day = d + timedelta(days=utc_shift_days)
        (hid, hname), (aid, aname) = TEAMS[h], TEAMS[a]
        fx.append(fdh.FmFixture(
            id=str(9000 + i), day=day, utc=f"{day.isoformat()}T14:00:00Z", round=str(i // 2 + 1),
            home_id=hid, away_id=aid, home_name=hname, away_name=aname, home_short=hname, away_short=aname,
            finished=True, cancelled=False, awarded=False, hs=hg, as_=ag, score_str=f"{hg} - {ag}"))
    return fx


def test_fotmob_season_and_score_parsing():
    assert fdh.fotmob_season("2122") == "2021/2022"
    assert fdh.fotmob_season("2526") == "2025/2026"
    with pytest.raises(ValueError):
        fdh.fotmob_season("21/22")
    assert fdh.parse_score("2 - 1") == (2, 1)
    assert fdh.parse_score("10-0") == (10, 0)
    assert fdh.parse_score("") is None
    assert fdh.parse_score(None) is None
    assert fdh.parse_score("1 - 1 (4 - 3)") is None  # never half-parse an unexpected format


def test_anchors_then_opponent_votes_map_every_team_and_row():
    sched = _schedule()
    rows, idx = _fd_rows(sched), fdh.FixtureIndex(_fixtures(sched))
    anchors = {"Alpha (test)": "101", "Beta (test)": "102"}
    tm = fdh.map_teams(rows, idx, anchors)
    assert tm.mapping == {n: t[0] for n, t in TEAMS.items()}
    assert tm.details["Alpha (test)"]["method"] == "existing_map_anchor"
    assert tm.details["Gamma (test)"]["method"] == "opponent_fixture_votes"
    assert all(d["pair_hits"] == d["pair_n"] for d in tm.details.values())
    res = fdh.map_rows(rows, idx, tm.mapping)
    assert [r["status"] for r in res] == ["mapped"] * len(rows)
    assert len({r["fixture"].id for r in res}) == len(rows)


def test_contradicted_anchor_is_dropped_and_remapped():
    sched = _schedule()
    rows, idx = _fd_rows(sched), fdh.FixtureIndex(_fixtures(sched))
    # synthetic wrong anchor: Gamma pointed at Delta's id
    anchors = {"Alpha (test)": "101", "Beta (test)": "102", "Gamma (test)": "104"}
    tm = fdh.map_teams(rows, idx, anchors)
    assert tm.mapping["Gamma (test)"] == "103"
    assert tm.mapping["Delta (test)"] == "104"
    assert tm.details["Gamma (test)"]["method"] != "existing_map_anchor"


def test_score_overlap_works_without_any_anchor():
    sched = _schedule()
    rows, idx = _fd_rows(sched), fdh.FixtureIndex(_fixtures(sched))
    tm = fdh.map_teams(rows, idx, {})
    assert tm.mapping == {n: t[0] for n, t in TEAMS.items()}
    assert "score_fixture_overlap" in {d["method"] for d in tm.details.values()}


def test_rows_need_the_pair_within_one_day():
    sched = _schedule()
    # row 0 dated one day after FotMob (UTC date differences): still mapped
    # row 1 dated three days off: not mapped, nearest fixture reported
    rows = _fd_rows(sched, day_shift={0: 1, 1: 3})
    idx = fdh.FixtureIndex(_fixtures(sched))
    mapping = {n: t[0] for n, t in TEAMS.items()}
    res = fdh.map_rows(rows, idx, mapping)
    assert res[0]["status"] == "mapped" and res[0]["fixture"].id == "9000"
    assert res[1]["status"] == "no_fixture" and res[1]["fixture"] is None
    assert res[1]["nearest"].id == "9001"
    assert all(r["status"] == "mapped" for r in res[2:])


def test_unmapped_team_rows_are_reported_not_guessed():
    sched = _schedule()
    rows, idx = _fd_rows(sched), fdh.FixtureIndex(_fixtures(sched))
    mapping = {n: t[0] for n, t in TEAMS.items() if n != "Delta (test)"}
    res = fdh.map_rows(rows, idx, mapping)
    delta = [r for r in res if "Delta (test)" in (r["row"].home, r["row"].away)]
    assert delta and all(r["status"] == "unmapped_team" and r["fixture"] is None for r in delta)
    assert all("Delta (test)" in r["reason"] for r in delta)


def test_one_fixture_cannot_back_two_rows():
    sched = _schedule()
    rows = _fd_rows(sched)
    rows.append(rows[0])  # synthetic duplicate football-data row
    idx = fdh.FixtureIndex(_fixtures(sched))
    res = fdh.map_rows(rows, idx, {n: t[0] for n, t in TEAMS.items()})
    assert res[0]["status"] == "ambiguous" and res[-1]["status"] == "ambiguous"
    assert res[0]["fixture"] is None


def test_output_row_probabilities_use_the_same_method_and_scores_compare():
    sched = _schedule()
    rows, idx = _fd_rows(sched), fdh.FixtureIndex(_fixtures(sched))
    raw = {"AvgCH": "2.00", "AvgCD": "4.00", "AvgCA": "4.00",  # synthetic odds, no Pinnacle closing
           "PC>2.5": "1.90", "PC<2.5": "2.00", "PSH": "2.10", "PSD": "3.50", "PSA": "3.60",
           "Avg>2.5": "1.80", "Avg<2.5": "2.10"}
    rows[0].raw = raw
    res = fdh.map_rows(rows, idx, {n: t[0] for n, t in TEAMS.items()})
    out = fdh.output_row(res[0], "E0", "2223", {"manifest_key": "2223/E0", "snapshot": "20240103011620"})
    assert out["close_1x2_source"] == "AvgCH"
    assert out["p_close_home"] == pytest.approx(0.5) and out["p_close_draw"] == pytest.approx(0.25)
    assert out["close_ou25_source"] == "PC>2.5"
    assert out["pre_ou25_source"] == "Avg>2.5"
    inv = 1 / 1.8 + 1 / 2.1
    assert out["p_pre_over25"] == round((1 / 1.8) / inv, 5)
    assert out["fotmob_match_id"] == "9000" and out["score_agrees"] == 1
    assert out["AvgCH"] == "2.00" and out["PSCH"] == ""  # missing source values stay empty
    # a row without any odds keeps empty probabilities (never zero)
    empty = fdh.output_row(res[1], "E0", "2223", {})
    assert empty["p_close_home"] == "" and empty["close_1x2_source"] == ""


def test_missing_awarded_flag_stays_empty_never_zero():
    # SYNTHETIC league response: FotMob omits 'awarded' for some fixtures (an abandoned match)
    def match(mid, status_extra):
        return {"id": mid, "round": "1", "home": {"id": 101, "name": "Alpha United (test)"},
                "away": {"id": 102, "name": "Beta City (test)"},
                "status": {"utcTime": "2022-08-06T14:00:00Z", "finished": True, "cancelled": False,
                           "scoreStr": "1 - 1", **status_extra}}
    data = {"fixtures": {"allMatches": [match("1", {}), match("2", {"awarded": True}), match("3", {"awarded": False})]}}
    fx = {f.id: f for f in fdh.parse_fotmob_fixtures(data)}
    assert fx["1"].awarded is None and fx["2"].awarded is True and fx["3"].awarded is False
    row = fdh.FdRow("2223", "E0", date(2022, 8, 6), "15:00", "Alpha (test)", "Beta (test)", 1, 1, "D", {})
    got = {mid: fdh.output_row({"row": row, "status": "mapped", "fixture": f}, "E0", "2223", {})["fotmob_awarded"]
           for mid, f in fx.items()}
    assert got == {"1": "", "2": 1, "3": 0}


def test_partial_season_file_is_labelled(monkeypatch):
    sched = _schedule()
    dicts = [{"Date": d.strftime("%d/%m/%Y"), "HomeTeam": h, "AwayTeam": a, "FTHG": str(hg), "FTAG": str(ag)}
             for d, h, a, hg, ag in sched]  # synthetic season file
    for n_rows, complete in ((len(dicts), True), (9, False)):
        monkeypatch.setattr(fdh, "fd_sources", lambda s, d, m, n=n_rows: [
            ("2223/E0", Path("synthetic.csv"), "20240101000000", lambda: dicts[:n])])
        rows, info = fdh.load_fd_file("2223", "E0", {})
        assert len(rows) == n_rows and info["complete"] is complete
        res = fdh.map_rows(rows[:1], fdh.FixtureIndex(_fixtures(sched)), {n: t[0] for n, t in TEAMS.items()})
        assert fdh.output_row(res[0], "E0", "2223", info)["fd_file_complete"] == int(complete)
    assert fdh.output_row(res[0], "E0", "2223", {})["fd_file_complete"] == ""  # unknown stays empty


def test_score_disagreement_is_flagged():
    sched = _schedule()
    rows, idx = _fd_rows(sched), fdh.FixtureIndex(_fixtures(sched))
    rows[2].hg = (rows[2].hg or 0) + 1
    res = fdh.map_rows(rows, idx, {n: t[0] for n, t in TEAMS.items()})
    assert fdh.output_row(res[2], "E0", "2223", {})["score_agrees"] == 0


def test_file_captures_picks_newest_http200_of_the_right_file():
    caps = [
        {"timestamp": "20211021064221", "original": "https://www.football-data.co.uk/mmz4281/2122/E0.csv",
         "statuscode": "200"},
        {"timestamp": "20240103011620", "original": "https://football-data.co.uk/mmz4281/2122/E0.csv",
         "statuscode": "200"},
        {"timestamp": "20250722182556", "original": "http://www.football-data.co.uk/mmz4281/2122/E0.csv",
         "statuscode": "301"},
        {"timestamp": "20250801000000", "original": "https://www.football-data.co.uk/mmz4281/2122/E1.csv",
         "statuscode": "200"},
    ]
    got = fdh.file_captures(caps, "2122", "E0")
    assert [c["timestamp"] for c in got] == ["20240103011620", "20211021064221"]
    assert fdh.file_captures(caps, "2122", "SP1") == []


def test_file_captures_accepts_revisits_of_an_identical_200_capture_only():
    caps = [
        {"timestamp": "20240910225850", "original": "https://www.football-data.co.uk/mmz4281/2324/E0.csv",
         "statuscode": "200", "mimetype": "text/csv", "digest": "AAA"},
        {"timestamp": "20260714192221", "original": "https://www.football-data.co.uk/mmz4281/2324/E0.csv",
         "statuscode": "-", "mimetype": "warc/revisit", "digest": "AAA"},
        {"timestamp": "20260801000000", "original": "https://www.football-data.co.uk/mmz4281/2324/E0.csv",
         "statuscode": "-", "mimetype": "warc/revisit", "digest": "ZZZ"},  # revisit of unknown content
        {"timestamp": "20250128215543", "original": "https://www.football-data.co.uk/mmz4281/2324/all-euro-data-2023-2024.xlsx",
         "statuscode": "200", "mimetype": "application/vnd.openxmlformats", "digest": "XLS"},
    ]
    assert [c["timestamp"] for c in fdh.file_captures(caps, "2324", "E0")] == ["20260714192221", "20240910225850"]
    assert [c["timestamp"] for c in fdh.file_captures(caps, "2324", None, name="all-euro-data-2023-2024.xlsx")] == [
        "20250128215543"]


def test_completeness_is_a_full_double_round_robin():
    sched = _schedule()
    dicts = [{"Date": d.strftime("%d/%m/%Y"), "HomeTeam": h, "AwayTeam": a, "FTHG": str(hg), "FTAG": str(ag)}
             for d, h, a, hg, ag in sched]
    full = fdh.summarize_rows(dicts, "2223", "E0")
    assert full["n_teams"] == 4 and full["double_round_robin_matches"] == 12 and full["complete"]
    part = fdh.summarize_rows(dicts[:9], "2223", "E0")
    assert part["n_rows"] == 9 and not part["complete"]
    assert fdh.summarize_rows(None, "2223", "E0")["complete"] is False


def _synthetic_xlsx(sheet_name, header, rows):
    """Minimal SYNTHETIC .xlsx (shared strings + numbers), built in memory for the parser test."""
    import io as _io
    import zipfile

    strings = []

    def s(v):
        if v not in strings:
            strings.append(v)
        return strings.index(v)

    def col(i):
        return chr(65 + i)

    xml_rows = []
    for r_i, row in enumerate([header] + rows, start=1):
        cells = []
        for c_i, v in enumerate(row):
            ref = f"{col(c_i)}{r_i}"
            if isinstance(v, str):
                cells.append(f'<c r="{ref}" t="s"><v>{s(v)}</v></c>')
            elif v is not None:
                cells.append(f'<c r="{ref}"><v>{v!r}</v></c>')
        xml_rows.append(f'<row r="{r_i}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rns}><sheets>'
                                      f'<sheet name="X9" sheetId="1" r:id="rId1"/>'
                                      f'<sheet name="{sheet_name}" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData></sheetData></worksheet>')
        z.writestr("xl/worksheets/sheet2.xml", f'<worksheet {ns}><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{v}</t></si>" for v in strings) + "</sst>")
    return buf.getvalue()


def test_xlsx_sheet_is_read_like_the_csv():
    # 45155 = 2023-08-17 (Excel 1900 system), 0.8125 = 19:30; synthetic odds/goals
    raw = _synthetic_xlsx("E0", ["Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "PSCH", "AvgCH"],
                          [["E0", 45155, 0.8125, "Alpha (test)", "Beta (test)", 2.0, 1, 1.9099999999999999, None]])
    rows = fdh.xlsx_sheet_dicts(raw, "E0")
    assert rows == [{"Div": "E0", "Date": "17/08/2023", "Time": "19:30", "HomeTeam": "Alpha (test)",
                     "AwayTeam": "Beta (test)", "FTHG": "2", "FTAG": "1", "PSCH": "1.91", "AvgCH": ""}]
    assert fdh.xlsx_sheet_dicts(raw, "I2") is None
    parsed, skipped = fdh.parse_fd_rows(rows, "2324", "E0")
    assert parsed[0].day == date(2023, 8, 17) and parsed[0].hg == 2 and skipped == 0
    assert fdh.bundle_division_dicts(raw, "all-euro-data-2023-2024.xlsx", "E0") == rows


def test_data_zip_member_is_read_like_the_csv():
    import io as _io
    import zipfile

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:  # SYNTHETIC bundle
        z.writestr("I2.csv", "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\r\nI2,19/08/2022,Gamma (test),Delta (test),0,0\r\n")
    rows = fdh.bundle_division_dicts(buf.getvalue(), "data.zip", "I2")
    assert rows == [{"Div": "I2", "Date": "19/08/2022", "HomeTeam": "Gamma (test)", "AwayTeam": "Delta (test)",
                     "FTHG": "0", "FTAG": "0"}]
    assert fdh.bundle_division_dicts(buf.getvalue(), "data.zip", "E0") is None


class _FakeResp:
    def __init__(self, status, body, headers=None):
        self.status_code, self.content, self.headers = status, body, headers or {}


class _FakeClient:
    """Replays SYNTHETIC responses; records the requests (no network)."""

    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.responses.pop(0)


def _patch_fotmob(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(fdh, "FOTMOB_LEAGUE_DIR", tmp_path)
    monkeypatch.setattr(fdh.fotmob_rate, "acquire", lambda *a, **k: events.append("acquire"))
    monkeypatch.setattr(fdh.fotmob_rate, "report_429", lambda s, *a, **k: events.append(("429", s)))
    monkeypatch.setattr(fdh.time, "sleep", lambda s: events.append(("sleep", s)))
    return events


def test_fotmob_fetch_uses_the_limiter_and_caches_the_untouched_body(monkeypatch, tmp_path):
    import gzip as _gzip
    import json as _json

    events = _patch_fotmob(monkeypatch, tmp_path)
    body = _json.dumps({"details": {"id": 999, "selectedSeason": "2021/2022"},
                        "fixtures": {"allMatches": []}}).encode()  # synthetic league response
    client = _FakeClient([_FakeResp(429, b"", {"Retry-After": "7"}), _FakeResp(200, body)])
    log = []
    data = fdh.fetch_fotmob_league(client, 999, "2021/2022", log)
    assert data["details"]["id"] == 999
    assert events.count("acquire") == 2 and ("429", 7) in events  # one acquire per HTTP request
    assert client.calls[0] == ("/api/data/leagues", {"id": 999, "season": "2021/2022"})
    cached = tmp_path / "999_2021-2022.json.gz"
    assert _gzip.decompress(cached.read_bytes()) == body
    assert not list(tmp_path.glob("*.tmp"))
    # cached now: no further request
    assert fdh.fetch_fotmob_league(_FakeClient([]), 999, "2021/2022", log)["details"]["id"] == 999


def test_fotmob_fetch_stops_on_403_and_on_a_challenge_page(monkeypatch, tmp_path):
    _patch_fotmob(monkeypatch, tmp_path)
    with pytest.raises(fdh.FotmobBlocked):
        fdh.fetch_fotmob_league(_FakeClient([_FakeResp(403, b"Forbidden")]), 998, "2021/2022", [])
    page = b"<!DOCTYPE html><html><body>Please complete the captcha challenge</body></html>"
    with pytest.raises(fdh.FotmobBlocked):
        fdh.fetch_fotmob_league(_FakeClient([_FakeResp(200, page, {"content-type": "text/html"})]), 998, "2021/2022", [])
    assert not list(tmp_path.iterdir())  # nothing cached


def test_fotmob_fetch_never_caches_another_season(monkeypatch, tmp_path):
    import json as _json

    _patch_fotmob(monkeypatch, tmp_path)
    body = _json.dumps({"details": {"id": 997, "selectedSeason": "2026/2027"}}).encode()  # synthetic
    assert fdh.fetch_fotmob_league(_FakeClient([_FakeResp(200, body)]), 997, "2021/2022", []) is None
    assert not list(tmp_path.iterdir())
