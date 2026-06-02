"""Derive the append-only transaction event log from player game logs.

For each player, games are ordered by date and runs of the same team are collapsed.
The first team a player appears with is a ``season_start`` membership; every later
change of ``TEAM_ABBREVIATION`` is a ``move`` (trade / waive+sign — indistinguishable
from box scores alone), dated at the first game played for the new team. This is the
"played for team X through game 3, team Y from game 4" reconstruction: deterministic,
look-ahead-free, exactly dated.

Caveat: game logs only cover players who actually played, and a player simply
disappearing at season end cannot be told apart from a waive. Roster snapshots would
complement this for completeness; here we capture real, dated *moves*.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

TRANSACTION_COLUMNS = [
    "date",
    "transaction_id",
    "event_type",
    "player_id",
    "player_name",
    "team",
    "note",
]


def derive_transactions(boxscores: pd.DataFrame, season: str | None = None) -> pd.DataFrame:
    df = boxscores[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_DATE"]].copy()
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
    df = df.sort_values(["PLAYER_ID", "GAME_DATE"], kind="stable")

    # A row is an event iff the player's team differs from their previous game's team.
    df["prev_team"] = df.groupby("PLAYER_ID")["TEAM_ABBREVIATION"].shift()
    changes = df[df["TEAM_ABBREVIATION"] != df["prev_team"]]

    event_type = changes["prev_team"].isna().map({True: "season_start", False: "move"})
    date = changes["GAME_DATE"].dt.strftime("%Y-%m-%d")
    player_id = changes["PLAYER_ID"].astype(str)
    prefix = f"{season}-" if season else ""
    note = "derived from game logs" + (f"; season={season}" if season else "")

    events = pd.DataFrame(
        {
            "date": date.to_numpy(),
            "transaction_id": (
                prefix + event_type.to_numpy() + "-" + player_id.to_numpy()
                + "-" + date.str.replace("-", "", regex=False).to_numpy()
            ),
            "event_type": event_type.to_numpy(),
            "player_id": player_id.to_numpy(),
            "player_name": changes["PLAYER_NAME"].to_numpy(),
            "team": changes["TEAM_ABBREVIATION"].to_numpy(),
            "note": note,
        }
    )
    return (
        events.sort_values(["date", "player_name"], kind="stable")
        .reset_index(drop=True)[TRANSACTION_COLUMNS]
    )


def main() -> None:
    params = yaml.safe_load(Path("params.yaml").read_text())
    season = params["ingest"]["season"]
    boxscores = pd.read_parquet(Path("data/raw/boxscores") / f"{season}.parquet")

    events = derive_transactions(boxscores, season=season)
    out_path = Path("data/raw/transactions.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(out_path, index=False)

    n_moves = int((events["event_type"] == "move").sum())
    print(
        f"Derived {len(events)} transaction events ({n_moves} mid-season moves) "
        f"from {len(boxscores)} game rows -> {out_path}"
    )


if __name__ == "__main__":
    main()
