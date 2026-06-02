# STORY.md — Demo-Log / Story-Anker

Chronologisches Log der Momente, die zeigen, *warum* dieser MLOps-Loop sich lohnt.
Jeder Eintrag ist eine kleine, reproduzierbare Geschichte: Auslöser → was passiert ist →
warum es zählt. Gedacht als roter Faden fürs Portfolio (README/Präsentation verweisen hierauf).

---

## 2026-06-02 — Eine Transaktion propagiert automatisch ins Roster

**Auslöser:** Eine einzelne Zeile an `data/raw/transactions.csv` angehängt — ein Trade
am 2025-09-20: `P5 (Echo Forward)` LAL→GSW, `P4 (Delta Wing)` GSW→LAL.

**Was passiert ist:** `dvc add data/raw/transactions.csv` → `dvc repro`. Nur die
`build_rosters`-Stage lief erneut; die Roster-Snapshots wurden neu abgeleitet — ohne dass
irgendein Roster manuell editiert wurde.

```
Roster @ 2025-09-16 (vor Trade)      Roster @ 2025-09-21 (nach Trade)
  BOS: [P3]                            BOS: [P3]
  GSW: [P4, P6]                        GSW: [P5, P6]   ← P5 rein
  LAL: [P1, P5]                        LAL: [P1, P4]   ← P4 rein
```

**Point-in-time-Check:** Roster @ 2025-09-19 bleibt unverändert (`GSW: [P4, P6]`,
`LAL: [P1, P5]`). Die Zukunfts-Transaktion leakt nicht in die Vergangenheit.

**Warum es zählt:** Belegt das Leitprinzip der Spec — wir modellieren die
Roster-Komposition, nicht „Team X". Ein Trade ist nur ein Event im append-only Log und
propagiert deterministisch durch die Pipeline. DVC trackt jede Transaktion als
Daten-Version-Event; `dvc repro` rebaut exakt das Nötige.

---

## 2026-06-02 — Pipeline läuft auf echten NBA-Daten

**Auslöser:** `pull_transactions`-Stage gebaut — zieht via `nba_api`
(`commonteamroster`) die echten Roster aller 30 Teams und schreibt sie als
`roster_snapshot`-Events ins `transactions.csv`-Schema.

**Was passiert ist:** `dvc repro` lief end-to-end: `pull_transactions → build_rosters`.
**534 echte Spieler-Membership-Events über 30 Teams** (Saison 2024-25) wurden gezogen und
in point-in-time Roster-Snapshots überführt — z.B. BOS mit Tatum, Brown, White, Holiday,
Porziņģis, Horford.

**Design-Entscheidung:** `nba_api` hat keinen Transaktions-Event-Feed. Statt ihn zu
faken, seeden wir den append-only Log aus echten Roster-Snapshots. Diffs zwischen
wiederholten (nightly/weekly) Pulls liefern später echte Trade-/Signing-/Waive-Events —
derselbe Log, nur von einer automatisierten Quelle gefüttert.

**Warum es zählt:** Die „laufende Datenquelle" der Spec ist jetzt real, nicht synthetisch.
`transactions.csv` ist von einem `dvc add`-Artefakt zu einem echten Pipeline-**Stage-Output**
geworden; `dvc dag` zeigt die Verkettung. Damit steht die Grundlage für echten Drift
(Free Agency ab Juli, Season Start im Oktober).

---

## 2026-06-02 — Transactions aus Game-Logs *abgeleitet* (statt gescraped)

**Auslöser:** Frage im Review — „Transactions sollte man doch aus den Rosters
reproduzieren können: Spieler spielt bis Spiel 3 bei Team X, ab Spiel 4 bei Team Y?"
Berechtigt: der erste Scraper datierte alle 534 Events auf *einen* Tag (Season-Start),
es gab also keine Mid-Season-Dynamik.

**Was passiert ist:** Architektur in drei Stages aufgetrennt —
`pull_boxscores → derive_transactions → build_rosters`.
- `pull_boxscores`: ein `LeagueGameLog`-Call liefert **26.306 Spieler-Spiele** (569 Spieler)
  mit Team-Zugehörigkeit pro Spiel — immutable, look-ahead-frei.
- `derive_transactions`: kollabiert pro Spieler aufeinanderfolgende Team-Runs; jeder
  Wechsel der `TEAM_ABBREVIATION` = ein `move`, datiert auf das **erste Spiel mit dem
  neuen Team**. Ergebnis: **656 Events, davon 87 echte Mid-Season-Moves**.

**Verifikation (Patty Mills, UTA→LAC):**
```
2024-10-23  season_start  UTA
2025-02-04  move          LAC
Roster-Check:  2025-02-03 -> UTA   |   2025-02-04 -> LAC
```

**Warum es zählt:** Die SPEC-Reihenfolge bleibt erhalten (transactions = kanonische
Wahrheit, Rosters daraus abgeleitet) — wir füttern den Event-Log nur aus *beobachtbaren*
Daten statt von Hand. Point-in-time ist jetzt auf echten Daten real: 107 datierte
Roster-Snapshots über die Saison. `nba_api` hat keinen Transaktions-Feed; Game-Logs sind
die ehrlichere, exaktere Quelle. (Caveat: erfasst nur Spieler, die gespielt haben;
Waive vs. Saisonende nicht unterscheidbar — Roster-Snapshots würden das später ergänzen.)

---

## 2026-06-02 — Erste Player Ratings, und der Sanity-Check stimmt

**Auslöser:** Erster Modell-Feature-Step — Spieler-Ratings aus den schon gezogenen
Box-Scores (`player_ratings`-Stage).

**Was passiert ist:** Aus 26.306 Spieler-Spielen → ein league-zentriertes, box-score-
basiertes Rating pro Spieler (Hollinger Game Score / 36 min, value-over-average).
**569 Spieler, 457 davon `reliable`** (≥200 Minuten).

**Sanity-Check (Top 10 reliable):**
```
Jokić 15.6 · Gilgeous-Alexander 14.7 · Antetokounmpo 13.9 · Williamson 11.5
Davis 9.8 · Dončić 9.0 · Wembanyama 8.6 · Embiid 7.9 · James 7.4 · Curry 7.3
```
Liga-Mittel (minuten-gewichtet) = 0.0001 → Zentrierung korrekt.

**Warum es zählt:** Das Rating ist eine **Spieler**-Eigenschaft (über alle Spiele, team-
agnostisch) — exakt die Roster-Komposition-Philosophie. Die Methodik ist bewusst
transparent und per `params.yaml` austauschbar (`box_gmsc` jetzt, BPM/EPM/RAPM später);
dokumentiert in `docs/methodology.md`. Damit steht die Basis für Minutes-Projection und
das minuten-gewichtete Team-Aggregat.

---

<!-- Nächste Story-Anker (geplant):
- September 2026: Win-Total-Projektionen committen — die Vor-Saison-Festlegung.
- Oktober 2026: Season Start als Drift-Validierungs-Event, Umschalten auf inseason.
- Erste Champion/Challenger-Promotion in mlflow.
-->
