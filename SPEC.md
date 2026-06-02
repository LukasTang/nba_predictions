# SPEC.md — NBA Roster-Based Prediction (MLOps Showcase)

Briefing-Dokument für den Aufbau. Ziel ist **nicht** ein State-of-the-Art-Vorhersagemodell,
sondern ein sauberer MLOps-Loop, in dem DVC und mlflow *zwingend* statt dekorativ sind:
laufende Datenquelle, echter Drift (Trades + Season Start), versioniertes Retraining,
Champion/Challenger-Promotion und Drift-Monitoring.

## Leitprinzip

Wir modellieren **nicht das Team**, sondern die **Roster-Komposition aus Spieler-Ratings**.
Team-Features werden bottom-up aus Spieler-Ratings aggregiert, gewichtet mit *projizierten*
Minuten. Ein Trade ist dann nur eine Änderung der Spieler-Zugehörigkeit und propagiert
automatisch — kein Bruch in einer gelernten "Team-X"-Beziehung.

## Nicht-verhandelbare Design-Constraints

1. **Roster als append-only Event-Log.** `transactions.csv` (Trades/Signings/Draft als Events)
   ist die einzige Wahrheit. Rosters werden daraus *abgeleitet*, nie direkt editiert.
   Jede Transaktion = ein DVC-Daten-Version-Event.
2. **Point-in-time-Korrektheit.** Der Roster zu Datum X muss exakt so rekonstruierbar sein,
   wie er an Datum X war. Kein zukünftiges Trade-Wissen in vergangenen Vorhersagen
   (Look-ahead-Bias). Dafür gibt es einen expliziten Test (siehe `tests/`).
3. **Minutes-Projection als eigener Step.** Team-Aggregat = Spieler-Ratings × *projizierte*
   Minuten, nicht Vorsaison-Minuten.
4. **Transfer-Logik bei Teamwechsel.** Kontextarme Metriken (Rebounds, eigene TS%) übertragen
   sich gut; kontextlastige (Assists, On/Off, Plus-Minus) schlecht → regression-to-mean
   + Unsicherheits-Inflation für gewechselte Spieler.
5. **Zwei-Modus-Pipeline** (per `params.yaml` umschaltbar):
   - **offseason**: Trigger = Transaktionen. Deliverable = Win-Total-Projektion pro Team,
     versioniert in mlflow, Benchmark = Vegas O/U Win-Totals.
   - **inseason**: Trigger = nightly Box-Scores. Scheduled Retraining, Champion/Challenger,
     Per-Game-Kalibrierung + Drift-Report.

## Repo-Layout

```
nba-mlops/
├── data/                        # DVC-tracked, NICHT in git
│   ├── raw/
│   │   ├── transactions.csv      # append-only Event-Log
│   │   └── boxscores/            # nightly pulls, partitioniert nach Datum
│   ├── interim/
│   │   └── rosters/              # rosters/{date}.parquet, abgeleitet
│   └── processed/
│       ├── player_ratings.parquet
│       └── team_features.parquet
├── src/
│   ├── ingest/
│   │   ├── pull_transactions.py
│   │   └── pull_boxscores.py     # nba_api, inseason
│   ├── features/
│   │   ├── build_rosters.py      # point-in-time Rekonstruktion aus transactions
│   │   ├── player_ratings.py
│   │   ├── minutes_projection.py
│   │   └── team_aggregate.py     # minutes-gewichtete Spieler-Ratings + Transfer-Logik
│   ├── models/
│   │   ├── train.py
│   │   ├── evaluate.py           # Backtest mit point-in-time Rosters
│   │   └── promote.py            # Champion/Challenger Registry-Logik
│   ├── monitoring/
│   │   └── drift_report.py       # Evidently
│   └── config.py
├── dvc.yaml
├── params.yaml
├── .gitlab-ci.yml
├── tests/
│   └── test_point_in_time.py     # garantiert kein Look-ahead-Leak
├── requirements.txt
├── README.md
└── SPEC.md
```

## DVC-Stages (dvc.yaml)

| Stage              | deps                                   | outs                          |
|--------------------|----------------------------------------|-------------------------------|
| pull_transactions  | src/ingest/pull_transactions.py        | data/raw/transactions.csv     |
| pull_boxscores     | src/ingest/pull_boxscores.py           | data/raw/boxscores/           |
| build_rosters      | transactions.csv, build_rosters.py     | data/interim/rosters/         |
| player_ratings     | boxscores/, player_ratings.py          | processed/player_ratings.pq   |
| minutes_projection | rosters/, player_ratings.pq            | processed/minutes.pq          |
| team_features      | ratings + minutes + rosters            | processed/team_features.pq    |
| train              | team_features.pq, params.yaml          | mlflow run (model artifact)   |
| evaluate           | model, team_features.pq                | metrics.json                  |
| drift_report       | team_features.pq (current vs ref)      | reports/drift.html            |

`dvc dag` muss sauber durchlaufen. Stages über `params.yaml` parametrisieren, damit
`dvc repro` deterministisch ist.

## params.yaml (Skizze)

```yaml
mode: offseason          # offseason | inseason
season: "2026-27"
ratings:
  metric: bpm            # box-score-basiert zum Start, EPM/RAPM später
minutes:
  source: depth_chart
transfer:
  context_light: [reb, ts_pct]
  context_heavy: [ast, plus_minus]
  regression_to_mean: 0.4
  uncertainty_inflation: 1.5
model:
  type: gradient_boosting
  target: win_prob       # offseason: win_total
promotion:
  metric: brier_score    # inseason; offseason: win_total_mae_vs_vegas
  min_improvement: 0.005
```

## mlflow — Registry & Promotion

- Jeder `train`-Run loggt Params, Metriken, Modell-Artefakt + Kalibrierungs-Plot.
- `promote.py`: Challenger wird gegen den aktuellen Champion auf der Holdout-/Backtest-Metrik
  verglichen. Promotion nur bei Verbesserung > `min_improvement`. Stages im Registry taggen
  (champion/challenger/archived).
- **Story-Anker:** Im September einmal die Win-Total-Projektionen committen ("die Modell-
  version, auf die ich mich vor der Saison festgelegt habe") und ab Oktober den
  Projektionsfehler über die Saison tracken.

## GitLab CI (.gitlab-ci.yml)

- **offseason**: scheduled `weekly` → pull_transactions → repro → ggf. neue Win-Total-Projektion.
- **inseason**: scheduled `nightly` → pull_boxscores → repro → train → evaluate → promote → drift_report.
- Pipeline failt, wenn `test_point_in_time` failt oder Drift einen Threshold reißt.

## Timeline (spielt uns in die Karten)

- **Juni/Juli**: Infra bauen. Draft (Ende Juni) + Free Agency (ab ~1. Juli) liefern echte
  Transaktions-Events → perfekt zum Testen des DVC-Versioning.
- **September**: Win-Total-Projektionen committen (Vor-Saison-Festlegung).
- **Mitte/Ende Oktober**: Season Start = großes Drift-Validierungs-Event, Umschalten auf inseason.

## Definition of Done (für ein überzeugendes Portfolio)

- [ ] `dvc repro` end-to-end reproduzierbar, `dvc dag` sauber
- [ ] Transaktion hinzufügen → Roster + Team-Features propagieren automatisch
- [ ] `test_point_in_time` grün (kein Look-ahead-Leak)
- [ ] mlflow zeigt ≥2 Modellversionen mit Champion/Challenger-Vergleich
- [ ] Drift-Report wird automatisch erzeugt
- [ ] CI-Schedule (offseason weekly) läuft grün
- [ ] README erklärt die Roster-as-Event-Log-Idee in 5 Sätzen
