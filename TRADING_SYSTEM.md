# OpenClaw - Trading System
Version: 5.2
Date: 2026-04-26
Status: Verbindlich

---

## 1. Scope

Dieses Dokument regelt ausschliesslich die Trading-Lane:
- Zielsteuerung
- Research
- Strategieentscheidungen
- Monitoring und Limits
- Capability-Bedarf an die Software-Lane

---

## 2. Kanonische Trading-Artefakte

1. `TRADING_STATE.md`
- Operativer Ist-Zustand fuer Trading (Mode, Limits, relevante Betriebsdaten).

2. Externes Goal-System
- Quelle fuer Trading-Ziele: `trading-cli goals` oder Trading-DB.
- Trading-Ziele werden nicht im SW-Requirements-Katalog gefuehrt.

---

## 3. Integrierte Governance (Constitution fuer Trading-Lane)

### 3.1 Rollen-Charter

- `trading-analyst`: Evidenz und Unsicherheitsbild.
- `trading-strategist`: Entscheidet promote/hold/reject und priorisiert Ziele.
- `trading-sentinel`: Monitoring, Limits, Anomalien, Blocker.
- `nexus`: Gate fuer Routing/Handoff in die Software-Lane.

### 3.2 Autoritaet in der Trading-Lane

| Action | trading-strategist | trading-analyst | trading-sentinel | nexus |
|---|---|---|---|---|
| Trading goals (extern) pflegen | Execute/Decide | Propose | Propose | Propose |
| Trading-Strategieentscheidungen | Execute/Decide | Propose | Propose | Propose |
| Trading-Monitoring/Alerts | Propose | Propose | Execute/Decide | Propose |
| Capability-Gap-Handoff Trading -> SW | Propose | Propose | Propose | Gate |

### 3.3 Harte Grenzen

- Trading-Rollen schreiben keinen Produktionscode.
- Trading-Rollen editieren keinen SW-Requirements-Katalog/-State direkt.
- Kein Capability-Bedarf ohne formalen Handoff.

---

## 4. Verbindlicher Trading-Workflow

1. Zielsteuerung:
- Ziele werden im externen Goal-System gepflegt.

2. Analyse:
- Analyst liefert strukturierte Ergebnisse.

3. Entscheidung:
- Strategist trifft Richtungsentscheidung.

4. Monitoring:
- Sentinel prueft Limits/Systemgesundheit und meldet Abweichungen.

5. Capability-Bedarf:
- Bei fehlender Capability wird ein formaler Handoff an die Software-Lane erzeugt.
- Capability-Preflight vor Strategie-/Handoff-Entscheidungen ist verpflichtend; die normative CLI-Regel liegt in [NEXUSCTL_FUNCTIONS.md](NEXUSCTL_FUNCTIONS.md).
- Die Trading-Lane ist berechtigt, fuer diesen Preflight primaer `nexusctl context` zu nutzen; kompatibel bleiben `auth` + `capabilities list/show`.
- Die Trading-Lane darf auf Basis dieser CLI-Informationen Capability-Bedarf vorschlagen; die finale Handoff-Einreichung bleibt bei `trading-strategist`.

---

## 5. Handoff an Software (Pflicht)

Trading erstellt bei Capability-Luecke einen formalen Handoff.
Feldschema, Validierung, Lifecycle, SLA, Eskalation, DoR/DoD und Audit sind ausschliesslich hier normiert:
- [HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md](HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md)

---

## 6. Einbahnregel zur Software-Lane

1. Trading muss den Software-Capability-Status kennen.
2. Software muss Trading-Ziele nicht kennen, nur den Handoff-Vertrag.
3. Adoption bleibt Trading-Entscheidung nach gelieferter Capability.
