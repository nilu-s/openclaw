# OpenClaw - Documentation Ownership Matrix
Version: 2.0
Date: 2026-04-30
Status: Verbindlich

---

## 1. Ziel

Diese Matrix legt fest, welche Datei die Single Source of Truth pro Thema ist und welche Kurzreferenzen in anderen Dateien erlaubt sind.

---

## 2. Ownership-Matrix

| Thema | Master-Datei (Single Source of Truth) | Erlaubte Kurzreferenz in anderen Dateien |
|---|---|---|
| Doku-Schachtelung, Domain-Grenzen, Leseregel | [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | 1-3 Zeilen Zweck + Link |
| Trading-Rollen, Trading-Workflow, Trading-Grenzen | [TRADING_SYSTEM.md](TRADING_SYSTEM.md) | 1-3 Zeilen Trading-Pflicht + Link |
| SW-Rollen, SW-Workflow, SW-Governance inkl. Inhaltsstandard fuer Requirements-Katalog/State | [SOFTWARE_DEVELOPMENT_SYSTEM.md](SOFTWARE_DEVELOPMENT_SYSTEM.md) | 1-3 Zeilen SW-Pflicht + Link |
| Git-Workflow (Branching, PR, Merge-Gate, Hotfix) | [SOFTWARE_DEVELOPMENT_SYSTEM.md](SOFTWARE_DEVELOPMENT_SYSTEM.md) | 1-3 Zeilen Git-Hinweis + Link |
| Runtime, Deployment, Pfade, Container-Topologie | [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md) | 1-3 Zeilen Runtime-Hinweis + Link |
| Trading->Software Handoff (Felder, Status, SLA, Eskalation, DoR/DoD, Audit) | [HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md](HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md) | 1-3 Zeilen "formaler Handoff + Link" |
| DB/CLI-Transformationsplan (MVP: Capability-Transparenz) | [REQUIREMENTS_CLI_DB_PLAN.md](REQUIREMENTS_CLI_DB_PLAN.md) | 1-3 Zeilen Planungsstatus + Link |
| `nexusctl` Command-/Session-/Rechte-Spezifikation inkl. Capability-Preflight | [NEXUSCTL_FUNCTIONS.md](NEXUSCTL_FUNCTIONS.md) | 1-3 Zeilen CLI-Hinweis + Link |
| SW-Requirements-Katalog/State Standard | [SOFTWARE_DEVELOPMENT_SYSTEM.md](SOFTWARE_DEVELOPMENT_SYSTEM.md) | 1 Zeile "siehe Abschnitt 7" |

---

## 3. Normative Regeln fuer Doku-Konsistenz

1. Jede normative Aussage darf nur in einer Master-Datei stehen.
2. Andere Dateien duerfen nur Kurzreferenzen enthalten, keine doppelte Feld-, Status- oder SLA-Definition.
3. Bei Konflikt gilt immer die Master-Datei der Matrix.
4. Aenderungen erfolgen in dieser Reihenfolge:
- Master-Datei aktualisieren
- Kurzreferenzen pruefen/anpassen
- Version/Date in geaenderten Dateien aktualisieren
5. Bei Unsicherheit zur Zustaendigkeit entscheidet `SYSTEM_OVERVIEW.md` in Kombination mit dieser Matrix.
6. Capability-Preflight (`nexusctl auth`, Session-Nutzung, Re-Checks) darf nur in `NEXUSCTL_FUNCTIONS.md` normativ beschrieben werden; andere Dateien enthalten nur Kurzreferenz + Link.

---

## 4. Freigabe-Check bei Doku-Aenderungen

Vor Abschluss jeder Doku-Aenderung muss geprueft werden:
- Gibt es neue doppelte Feldlisten?
- Gibt es wiederholte Lifecycle- oder DoD-Definitionen ausserhalb der Master-Datei?
- Sind Git-Workflow-Regeln nur in der Master-Datei normativ definiert?
- Verweisen alle Kurzreferenzen auf die korrekte Master-Datei?
- Sind Requirements-Katalog und Requirements-State gemaess Inhaltsstandard (Feature/SF/FR-IDs + Status/Nachweise) gepflegt?
- Sind Version und Datum in geaenderten Dateien aktualisiert?
