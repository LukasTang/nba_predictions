"""Unit tests for box-score player ratings (no network)."""

import pandas as pd

from src.features.player_ratings import compute_player_ratings, game_score

BOX_COLUMNS = [
    "PLAYER_ID", "PLAYER_NAME", "GAME_ID", "MIN",
    "PTS", "FGM", "FGA", "FTM", "FTA", "OREB", "DREB", "STL", "AST", "BLK", "PF", "TOV",
]


def _row(pid, name, gid, minutes, pts, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov):
    return (pid, name, gid, minutes, pts, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov)


def _fake_boxscores() -> pd.DataFrame:
    rows = [
        # Star: high production, plenty of minutes (2 games).
        _row("P1", "Star", "G1", 36, 30, 11, 20, 6, 7, 1, 7, 1, 8, 1, 2, 3),
        _row("P1", "Star", "G2", 36, 28, 10, 19, 6, 6, 2, 6, 2, 7, 1, 1, 2),
        # Bench: low production, few minutes (1 game) -> not reliable.
        _row("P2", "Bench", "G1", 5, 2, 1, 3, 0, 0, 0, 1, 0, 0, 0, 1, 1),
    ]
    return pd.DataFrame(rows, columns=BOX_COLUMNS)


def test_game_score_matches_hollinger_formula():
    df = _fake_boxscores().iloc[[0]]
    # 30 +0.4*11 -0.7*20 -0.4*(7-6) +0.7*1 +0.3*7 +1 +0.7*8 +0.7*1 -0.4*2 -3
    expected = 30 + 0.4 * 11 - 0.7 * 20 - 0.4 * 1 + 0.7 * 1 + 0.3 * 7 + 1 + 0.7 * 8 + 0.7 * 1 - 0.4 * 2 - 3
    assert round(float(game_score(df).iloc[0]), 6) == round(expected, 6)


def test_one_row_per_player_and_schema():
    r = compute_player_ratings(_fake_boxscores(), season="2024-25", min_minutes=60)
    assert len(r) == 2
    assert {"player_id", "player_name", "season", "games", "minutes", "gmsc_per36", "box_rating", "reliable"} <= set(r.columns)
    assert r["player_id"].map(type).eq(str).all()


def test_reliable_flag_uses_min_minutes():
    r = compute_player_ratings(_fake_boxscores(), season="2024-25", min_minutes=60)
    rel = dict(zip(r["player_id"], r["reliable"]))
    assert rel["P1"] is True or bool(rel["P1"]) is True  # 72 min >= 60
    assert bool(rel["P2"]) is False                       # 5 min < 60


def test_box_rating_is_minutes_weighted_zero_centered():
    r = compute_player_ratings(_fake_boxscores(), season="2024-25")
    # Centering is exact before the stored 2-decimal rounding; the minutes-weighted
    # mean must therefore sit within half a rounding unit of zero.
    weighted_mean = (r["box_rating"] * r["minutes"]).sum() / r["minutes"].sum()
    assert abs(weighted_mean) < 0.005


def test_star_outrates_bench():
    r = compute_player_ratings(_fake_boxscores(), season="2024-25").set_index("player_id")
    assert r.loc["P1", "box_rating"] > r.loc["P2", "box_rating"]
