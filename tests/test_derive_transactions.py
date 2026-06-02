"""Unit tests for deriving transactions from game logs (no network)."""

import pandas as pd

from src.ingest.derive_transactions import TRANSACTION_COLUMNS, derive_transactions


def _fake_boxscores() -> pd.DataFrame:
    # P1: plays UTA games 1-3, then LAC games 4-5  -> one mid-season move.
    # P2: stays on BOS the whole time             -> only a season_start.
    rows = [
        ("P1", "Alpha", "UTA", "2024-10-23"),
        ("P1", "Alpha", "UTA", "2024-10-25"),
        ("P1", "Alpha", "UTA", "2024-10-28"),
        ("P1", "Alpha", "LAC", "2025-02-10"),
        ("P1", "Alpha", "LAC", "2025-02-12"),
        ("P2", "Bravo", "BOS", "2024-10-24"),
        ("P2", "Bravo", "BOS", "2024-11-01"),
    ]
    df = pd.DataFrame(rows, columns=["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_DATE"])
    return df


def test_schema():
    events = derive_transactions(_fake_boxscores(), season="2024-25")
    assert list(events.columns) == TRANSACTION_COLUMNS


def test_season_start_emitted_once_per_player():
    events = derive_transactions(_fake_boxscores(), season="2024-25")
    starts = events[events["event_type"] == "season_start"]
    assert sorted(starts["player_id"]) == ["P1", "P2"]
    # P1 starts on UTA (their first game), not LAC.
    assert starts.loc[starts["player_id"] == "P1", "team"].iloc[0] == "UTA"


def test_midseason_move_dated_at_first_game_with_new_team():
    events = derive_transactions(_fake_boxscores(), season="2024-25")
    moves = events[events["event_type"] == "move"]
    assert len(moves) == 1
    move = moves.iloc[0]
    assert move["player_id"] == "P1"
    assert move["team"] == "LAC"
    # Effective date = first game played for the new team, not the last with the old one.
    assert move["date"] == "2025-02-10"


def test_no_spurious_move_for_stable_player():
    events = derive_transactions(_fake_boxscores(), season="2024-25")
    assert events[(events["player_id"] == "P2") & (events["event_type"] == "move")].empty
