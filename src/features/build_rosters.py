"""Point-in-time roster reconstruction from the append-only transaction log.

The roster of a team at a given date is derived, never stored directly: for each
player, the most recent transaction on or before that date determines which team
(if any) they belong to. A trade is two membership events on the same date; a waive
moves a player to the free-agent pool (``FREE_AGENT``).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

FREE_AGENT = "FA"

TRANSACTION_COLUMNS = [
    "date",
    "transaction_id",
    "event_type",
    "player_id",
    "player_name",
    "team",
    "note",
]


def load_transactions(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"player_id": str})
    df["date"] = pd.to_datetime(df["date"])
    return df


def _latest_membership(transactions: pd.DataFrame, as_of) -> pd.DataFrame:
    """Last membership event per player on or before ``as_of``.

    File order breaks ties between events on the same date, so a same-day
    waive-then-sign resolves to the later row.
    """
    as_of = pd.to_datetime(as_of)
    past = transactions[transactions["date"] <= as_of]
    if past.empty:
        return past.copy()
    past = past.reset_index(names="_seq").sort_values(["date", "_seq"], kind="stable")
    return past.groupby("player_id", as_index=False).tail(1)


def roster_at(transactions: pd.DataFrame, as_of, team: str | None = None):
    """Active roster as of ``as_of``.

    With ``team`` set, returns a sorted list of player_ids on that team.
    Otherwise returns ``{team: [player_id, ...]}`` for all teams. Free agents
    are excluded.
    """
    latest = _latest_membership(transactions, as_of)
    if latest.empty:
        return [] if team is not None else {}
    active = latest[latest["team"] != FREE_AGENT]
    if team is not None:
        return sorted(active.loc[active["team"] == team, "player_id"].tolist())
    return {t: sorted(g["player_id"].tolist()) for t, g in active.groupby("team")}


def build_all_rosters(transactions: pd.DataFrame, out_dir: str | Path) -> Path:
    """Write one roster snapshot parquet per transaction date."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for d in sorted(transactions["date"].dt.normalize().unique()):
        latest = _latest_membership(transactions, d)
        snapshot = (
            latest[latest["team"] != FREE_AGENT][["player_id", "player_name", "team"]]
            .assign(as_of=pd.Timestamp(d))
            .sort_values(["team", "player_id"])
            .reset_index(drop=True)
        )
        snapshot.to_parquet(out / f"{pd.Timestamp(d):%Y-%m-%d}.parquet", index=False)
    return out


if __name__ == "__main__":
    tx = load_transactions(Path("data/raw/transactions.csv"))
    out = build_all_rosters(tx, Path("data/interim/rosters"))
    print(f"Wrote roster snapshots to {out}")
