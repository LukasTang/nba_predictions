"""Unit tests for the roster -> transaction-log transform (no network)."""

import pandas as pd

from src.ingest.pull_transactions import (
    TRANSACTION_COLUMNS,
    roster_to_events,
    season_start_date,
)


def _fake_roster() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "PLAYER_ID": [1628369, 201950],
            "PLAYER": ["Jayson Tatum", "Jrue Holiday"],
            "HOW_ACQUIRED": ["Draft", "Trade"],
        }
    )


def test_season_start_date():
    assert season_start_date("2024-25") == "2024-10-01"


def test_roster_to_events_schema_and_values():
    events = roster_to_events(_fake_roster(), "BOS", "2024-25", "2024-10-01")

    assert list(events.columns) == TRANSACTION_COLUMNS
    assert (events["event_type"] == "roster_snapshot").all()
    assert (events["team"] == "BOS").all()
    assert (events["date"] == "2024-10-01").all()
    # player_id must be string (real NBA PERSON_IDs, kept as identifiers).
    assert events["player_id"].map(type).eq(str).all()
    assert events.loc[events["player_name"] == "Jayson Tatum", "player_id"].iloc[0] == "1628369"
    assert "acquired=Draft" in events.loc[events["player_name"] == "Jayson Tatum", "note"].iloc[0]


def test_roster_to_events_without_how_acquired_column():
    df = _fake_roster().drop(columns=["HOW_ACQUIRED"])
    events = roster_to_events(df, "LAL", "2024-25", "2024-10-01")
    assert list(events.columns) == TRANSACTION_COLUMNS
    assert events["note"].str.endswith("acquired=").all()
