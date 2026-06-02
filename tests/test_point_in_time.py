"""Guarantees that roster reconstruction has no look-ahead leak.

A roster computed for date X must reflect only transactions known on or before X.
Future transactions appended to the log must never alter a past roster.
"""

import pandas as pd
import pytest

from src.features.build_rosters import FREE_AGENT, roster_at

# Scenario:
#   2025-06-26  draft   P1 -> BOS, P3 -> LAL
#   2025-07-01  signing P2 -> BOS
#   2025-07-10  trade   P1 BOS->LAL, P3 LAL->BOS
#   2025-08-01  waive   P2 -> FA
ROWS = [
    ("2025-06-26", "draft-1", "draft", "P1", "Alpha", "BOS", ""),
    ("2025-06-26", "draft-2", "draft", "P3", "Charlie", "LAL", ""),
    ("2025-07-01", "sign-1", "signing", "P2", "Bravo", "BOS", ""),
    ("2025-07-10", "trade-1", "trade", "P1", "Alpha", "LAL", ""),
    ("2025-07-10", "trade-1", "trade", "P3", "Charlie", "BOS", ""),
    ("2025-08-01", "waive-1", "waive", "P2", "Bravo", FREE_AGENT, ""),
]
COLUMNS = ["date", "transaction_id", "event_type", "player_id", "player_name", "team", "note"]


@pytest.fixture
def transactions() -> pd.DataFrame:
    df = pd.DataFrame(ROWS, columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_no_roster_before_first_transaction(transactions):
    assert roster_at(transactions, "2025-06-25") == {}
    assert roster_at(transactions, "2025-06-25", team="BOS") == []


def test_no_lookahead_player_not_present_before_joining(transactions):
    # P2 signs 2025-07-01; must be absent the day before.
    assert "P2" not in roster_at(transactions, "2025-06-30", team="BOS")
    assert "P2" in roster_at(transactions, "2025-07-01", team="BOS")


def test_trade_propagates_as_swap(transactions):
    # Before the trade.
    assert roster_at(transactions, "2025-07-09", team="BOS") == ["P1", "P2"]
    assert roster_at(transactions, "2025-07-09", team="LAL") == ["P3"]
    # On/after the trade date: P1 and P3 swap teams.
    assert roster_at(transactions, "2025-07-10", team="BOS") == ["P2", "P3"]
    assert roster_at(transactions, "2025-07-10", team="LAL") == ["P1"]


def test_waive_removes_player(transactions):
    assert "P2" in roster_at(transactions, "2025-07-31", team="BOS")
    assert "P2" not in roster_at(transactions, "2025-08-01", team="BOS")


def test_appending_future_transaction_does_not_change_past_roster(transactions):
    as_of = "2025-07-05"
    before = roster_at(transactions, as_of)

    future = pd.DataFrame(
        [("2025-09-15", "sign-2", "signing", "P9", "Foxtrot", "GSW", "")],
        columns=COLUMNS,
    )
    future["date"] = pd.to_datetime(future["date"])
    extended = pd.concat([transactions, future], ignore_index=True)

    after = roster_at(extended, as_of)
    assert before == after
