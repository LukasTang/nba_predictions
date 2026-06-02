# Methodik

Dieses Dokument hält die *fachlichen* Entscheidungen der Pipeline fest — was berechnet
wird, warum, und welche bewussten Vereinfachungen drinstecken. Das Projekt ist ein
**MLOps-Showcase**, kein SOTA-Vorhersagemodell: Metriken sind absichtlich transparent und
austauschbar (per `params.yaml`), nicht maximal akkurat.

---

## 1. Transaktionen aus Game-Logs ableiten

**Quelle:** `nba_api` `LeagueGameLog` (Spieler-Ebene) — eine Zeile pro Spieler-Spiel mit
`TEAM_ABBREVIATION` und `GAME_DATE`, in *einem* Request für die ganze Saison.

**Warum abgeleitet statt gescraped:** `nba_api` hat keinen Transaktions-/Event-Feed. Game-
Logs sind die *beobachtbare* Wahrheit (immutable, exakt datiert, kein Look-ahead). Pro
Spieler werden die Spiele nach Datum sortiert und aufeinanderfolgende Team-Runs kollabiert:

- **erstes Team** des Spielers in der Saison → `season_start`-Event
- **jeder Team-Wechsel** → `move`-Event, datiert auf das **erste Spiel mit dem neuen Team**

Das ist die „spielte bis Spiel 3 bei X, ab Spiel 4 bei Y"-Rekonstruktion: deterministisch,
look-ahead-frei. Der so erzeugte `transactions.csv` ist der kanonische append-only
Event-Log (SPEC-Constraint #1); `build_rosters` rekonstruiert daraus point-in-time Rosters.

**Bewusste Caveats:**
- Erfasst nur Spieler, die tatsächlich *gespielt* haben (verletzte/reine Bankspieler fehlen).
- „Spieler verschwindet am Saisonende" ist nicht von einem Waive unterscheidbar.
- → Roster-Snapshots (`commonteamroster`) würden das später für Vollständigkeit ergänzen
  (geplanter Hybrid). Game-Logs liefern dafür *exakte* Wechseldaten für echte Trades.

---

## 2. Player Ratings (`box_gmsc`)

Ein Rating ist eine Eigenschaft des **Spielers**, nicht des Teams — das ist der Kern der
Roster-Komposition-Idee. Wir aggregieren *alle* Spiele eines Spielers in der Saison,
unabhängig vom Team, für das er auflief.

### Metrik: Game Score (Hollinger), per 36 Minuten, league-zentriert

Pro Spiel (reine Box-Score-Größen):

```
GmSc = PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA−FTM)
       + 0.7·OREB + 0.3·DREB + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TOV
```

Aus den Saison-Summen:

- `gmsc_per36` = (Σ GmSc / Σ Minuten) · 36 — Rate-Normalisierung, reduziert Sample-Rauschen
  gegenüber einem Per-Game-Mittel.
- `box_rating` = (Spieler-Rate − liga-weite, minuten-gewichtete Durchschnitts-Rate) · 36.
  Dadurch ist der **minuten-gewichtete Liga-Mittelwert exakt 0**: ein durchschnittlicher
  Rotationsspieler liegt bei ~0, bessere positiv. Dieses „Value over average" ist natürlich
  minuten-gewichtbar bei der späteren Team-Aggregation.
- `reliable` = Minuten ≥ `ratings.min_minutes` (Default 200) — Stabilitäts-Flag für
  Kleinst-Stichproben.

### Sanity-Check (Saison 2024-25)

Top-`box_rating` (reliable): Jokić, Gilgeous-Alexander, Antetokounmpo, Williamson, Davis,
Dončić, Wembanyama, Embiid, James, Curry. Liga-Mittel (minuten-gewichtet) = ~0.0. Plausibel.

### Bewusste Vereinfachungen / Grenzen

- **Game Score ≠ BPM.** Game Score ist box-score-only und gewichtet offensive Produktion
  stark; Verteidigung jenseits von STL/BLK und Spielkontext fehlen.
- **Per 36 Minuten, nicht per 100 Possessions.** Echtes BPM ist per-Possession und
  team-/positions-adjustiert. Wir sparen uns die Possession-Schätzung bewusst.
- **Kontextlastige Größen** (Assists, Plus-Minus) übertragen sich laut SPEC schlecht bei
  Teamwechsel → das adressiert später die Transfer-Logik (regression-to-mean +
  Unsicherheits-Inflation), nicht das Rating selbst.

### Austauschbarkeit

`params.yaml → ratings.metric` schaltet die Metrik um. `box_gmsc` ist der transparente
Startpunkt; **BPM → EPM → RAPM** sind die in der SPEC vorgesehenen späteren Upgrades. Der
Rest der Pipeline (Minutes-Projection, Team-Aggregat) bleibt davon unberührt, solange das
Rating als „Wert pro 36 Minuten relativ zum Liga-Schnitt" interpretierbar bleibt.
