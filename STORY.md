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

<!-- Nächste Story-Anker (geplant):
- September 2026: Win-Total-Projektionen committen — die Vor-Saison-Festlegung.
- Oktober 2026: Season Start als Drift-Validierungs-Event, Umschalten auf inseason.
- Erste Champion/Challenger-Promotion in mlflow.
-->
