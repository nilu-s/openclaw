# OpenClaw - System Overview
Version: 5.4
Date: 2026-04-30
Status: Active

---

## 1. Zweck

Dieses Dokument ist der Einstiegspunkt in die gesamte Systemdokumentation.
Es definiert die Schachtelung, die Domain-Grenzen und die verbindliche Verbindung zwischen Trading und Software.

---

## 2. Dokumenten-Schachtelung

Level 0:
- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)

Level 1 Domains:
- [SOFTWARE_DEVELOPMENT_SYSTEM.md](SOFTWARE_DEVELOPMENT_SYSTEM.md)
- [TRADING_SYSTEM.md](TRADING_SYSTEM.md)

Level 1 Runtime:
- [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md)
- [HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md](HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md)
- [DOCUMENTATION_OWNERSHIP_MATRIX.md](DOCUMENTATION_OWNERSHIP_MATRIX.md)
- [REQUIREMENTS_CLI_DB_PLAN.md](REQUIREMENTS_CLI_DB_PLAN.md) (Draft, Konzeptphase)
- [NEXUSCTL_FUNCTIONS.md](NEXUSCTL_FUNCTIONS.md) (CLI-Funktionsspezifikation)

Software-Repo-Standard:
- Requirements-Katalog (DB-Objekt, verwaltet ueber `nexusctl`)
- Requirements-State (DB-Objekt, verwaltet ueber `nexusctl`)

Hinweis:
- Rollen- und Autoritaetsregeln sind in die beiden Domain-Dokumente integriert.
- Es gibt keine separate Verfassungsdatei mehr.

---

## 3. Verbindliche Trennung

1. Software-Lane:
- plant, baut, reviewed und liefert technische Capabilities.

2. Trading-Lane:
- steuert Ziele, Research, Entscheidungen und Monitoring.

3. Keine Vermischung:
- Trading-Ziele werden nicht im SW-Requirements-Katalog gepflegt.
- Software trifft keine Trading-Strategieentscheidungen.

---

## 4. Einbahnregel

1. Trading muss Software-Capabilities kennen (verfuegbar/nicht verfuegbar).
2. Software muss Trading-Ziele nicht kennen, ausser als formalisierte Requirement-Daten.
3. Domain-Uebergang erfolgt nur ueber den Handoff-Contract.
4. SW-Requirements werden ueber `nexusctl` verwaltet; lokale Snapshots sind nur abgeleitete Sichten.

---

## 5. Handoff-Contract Trading -> Software

Single Source of Truth:
- [HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md](HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md)

---

## 6. Leseregel

1. Scope unklar: zuerst dieses Dokument.
2. Frage zu Lieferung/Implementierung/Review: Software-Dokument.
   Frage zum erwarteten Inhalt von Requirements-Katalog/Requirements-State: Software-Dokument, Abschnitt 7.
   Frage zu Branching/PR/Merge/Hotfix: Software-Dokument, Abschnitt 8.
   Frage zur geplanten `nexusctl`-Einfuehrung: [REQUIREMENTS_CLI_DB_PLAN.md](REQUIREMENTS_CLI_DB_PLAN.md).
   Frage zu `nexusctl`-Befehlen/Parametern/Rechten: [NEXUSCTL_FUNCTIONS.md](NEXUSCTL_FUNCTIONS.md).
3. Frage zu Strategie/Research/Monitoring: Trading-Dokument.
4. Frage zu Pfaden/Container/Runtime: Architekturplan.
