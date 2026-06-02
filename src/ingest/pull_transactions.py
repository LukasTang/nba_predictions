"""Pull real NBA rosters and emit them as roster-snapshot events.

nba_api has no transaction-event feed, so the append-only event log is seeded from
``commonteamroster`` snapshots: one membership row per (player, team) for a season.
Each row uses the transaction-log schema with ``event_type="roster_snapshot"``. Diffing
snapshots from repeated (e.g. nightly/weekly) pulls later yields real signing / trade /
waive events — the same append-only log, just grown by an automated source.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yaml
from nba_api.stats.endpoints import commonteamroster
from nba_api.stats.static import teams as static_teams

TRANSACTION_COLUMNS = [
    "date",
    "transaction_id",
    "event_type",
    "player_id",
    "player_name",
    "team",
    "note",
]


def season_start_date(season: str) -> str:
    """``"2024-25"`` -> ``"2024-10-01"`` (nominal season-start snapshot date)."""
    start_year = int(season.split("-")[0])
    return f"{start_year}-10-01"


def roster_to_events(roster_df: pd.DataFrame, team_abbr: str, season: str, as_of: str) -> pd.DataFrame:
    """Transform one ``commonteamroster`` frame into transaction-log rows."""
    acquired = (
        roster_df["HOW_ACQUIRED"].astype(str)
        if "HOW_ACQUIRED" in roster_df.columns
        else pd.Series([""] * len(roster_df))
    )
    out = pd.DataFrame(
        {
            "date": as_of,
            "transaction_id": f"snapshot-{season}-{team_abbr}",
            "event_type": "roster_snapshot",
            "player_id": roster_df["PLAYER_ID"].astype(str),
            "player_name": roster_df["PLAYER"],
            "team": team_abbr,
            "note": "commonteamroster " + season + "; acquired=" + acquired,
        }
    )
    return out[TRANSACTION_COLUMNS]


def pull_transactions(
    season: str,
    as_of: str | None = None,
    sleep: float = 0.6,
    timeout: int = 30,
    max_failures: int = 3,
) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    """Pull rosters for all 30 teams; return (events, failures).

    Raises if more than ``max_failures`` teams fail, so a partial scrape never
    silently overwrites the log.
    """
    as_of = as_of or season_start_date(season)
    frames: list[pd.DataFrame] = []
    failures: list[tuple[str, str]] = []
    for team in static_teams.get_teams():
        try:
            resp = commonteamroster.CommonTeamRoster(
                team_id=team["id"], season=season, timeout=timeout
            )
            df = resp.get_data_frames()[0]
            frames.append(roster_to_events(df, team["abbreviation"], season, as_of))
        except Exception as exc:  # noqa: BLE001 - record and continue
            failures.append((team["abbreviation"], str(exc)[:120]))
        time.sleep(sleep)

    if len(failures) > max_failures:
        raise RuntimeError(f"Too many roster pulls failed ({len(failures)}): {failures}")

    events = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["team", "player_name"])
        .reset_index(drop=True)
    )
    return events, failures


def main() -> None:
    params = yaml.safe_load(Path("params.yaml").read_text())
    season = params["ingest"]["roster_snapshot_season"]
    out_path = Path("data/raw/transactions.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    events, failures = pull_transactions(season)
    events.to_csv(out_path, index=False)
    print(
        f"Wrote {len(events)} roster-membership events "
        f"for {events['team'].nunique()} teams ({season}) to {out_path}"
    )
    if failures:
        print(f"WARNING: {len(failures)} team(s) failed: {failures}")


if __name__ == "__main__":
    main()
