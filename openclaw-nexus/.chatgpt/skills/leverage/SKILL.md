---
name: leverage
description: Lokalisiert den wichtigsten konkreten Hebel, der OpenClaw Nexus aktuell am stärksten produktionsreifer macht. Verwenden, wenn der Nutzer wissen möchte, welcher nächste Punkt den größten Production-Readiness-Gewinn bringt, welches Risiko zuerst reduziert werden sollte, welche Arbeit den Betrieb am meisten entsperrt oder welcher einzelne nächste Schritt Richtung Produktionsbetrieb am wertvollsten ist.
metadata:
  project: openclaw-nexus
  version: "1.0"
---

# Leverage Skill

Dieser Skill priorisiert Produktionsreife. Er sammelt nicht nur mögliche Verbesserungen, sondern benennt den wichtigsten konkreten Hebel, der OpenClaw Nexus aktuell am stärksten produktionsreifer macht.

## 1. Aktivierung

Aktiviere diesen Skill bei Aufträgen wie:

- „Was macht uns am meisten produktionsreifer?"
- „Finde den größten Hebel für Production Readiness."
- „Was ist der wichtigste nächste Schritt Richtung Betrieb?"
- „Welches Risiko sollten wir zuerst reduzieren?"
- „Welche Verbesserung bringt aktuell am meisten?"
- „Lokalisier den größten Punkt, der die Software produktionsreifer macht."

Nicht aktivieren, wenn der Nutzer nur Projektkonsistenz prüfen möchte; dafür `drift` verwenden. Nicht aktivieren, wenn der Nutzer primär alte Ansätze finden möchte; dafür `legacy` verwenden.

## 2. Kernvertrag

1. Der Skill muss am Ende genau einen Haupthebel benennen.
2. Der Haupthebel muss konkret, prüfbar und in einem überschaubaren Arbeitspaket umsetzbar sein.
3. Eleganz, Architekturästhetik oder große Umbauten gewinnen nicht automatisch. Produktionsrisiko, Betriebssicherheit und Nachweisbarkeit zählen stärker.
4. Der Skill führt keine Umsetzung aus, außer der Nutzer verlangt ausdrücklich die Umsetzung.
5. Die Empfehlung muss aus dem aktuellen Projektzustand abgeleitet werden, nicht aus generischen Best Practices.

## 3. Quellenpriorität

Prüfe je nach Auftrag:

| Priorität | Quelle | Zweck |
| --- | --- | --- |
| 1 | `.chatgpt/state/CURRENT_STATE.md` | Bekannte Fähigkeiten, Grenzen und empfohlene nächste Arbeiten. |
| 2 | `README.md`, `docs/operations/*`, `docs/product/*` | Betriebsmodell, Produktversprechen und dokumentierte Grenzen. |
| 3 | Code und Tests | Tatsächliche Sicherheits-, Persistenz-, API-, CLI-, Audit- und Betriebsreife. |
| 4 | `config/*`, Docker, ENV-Beispiele | Deployment-, Secret-, Pfad- und Runtime-Annahmen. |
| 5 | Scripts | Validierung, Packaging, Backup/Restore und Betriebschecks. |
| 6 | `nexus/*.yml` und generierte Artefakte | Runtime-Policies, Agenten, Tools und Guardrails. |
| 7 | `.chatgpt/state/phases.md` | Laufender Arbeitsstand, falls vorhanden. |

## 4. Bewertungsdimensionen

Bewerte Kandidaten mit diesen Kriterien:

| Kriterium | Leitfrage |
| --- | --- |
| Risikoabbau | Welches echte Produktionsrisiko wird reduziert? |
| Betriebssicherheit | Hilft es bei Fehlern, Recovery, Diagnose oder sicheren Defaults? |
| Blocker-Wirkung | Entsperrt es weitere produktionsnahe Arbeiten? |
| Testbarkeit | Kann der Gewinn nach der Umsetzung eindeutig validiert werden? |
| Umsetzbarkeit | Passt es in ein überschaubares, kontrollierbares Arbeitspaket? |
| Nutzer-/Betreiberwert | Macht es die Software für interne Betreiber konkret brauchbarer? |
| Irreversibilität | Verhindert es spätere Sackgassen oder riskante Migrationen? |
| Drift-/Legacy-Bezug | Reduziert es bekannte Drift- oder Legacy-Risiken? |

## 5. Kandidatenfelder

Prüfe insbesondere diese Felder, ohne dich darauf zu beschränken:

- Backup-/Restore-Verifikation und Restore-Übungen
- Event-Store-Integrität, Audit-Export, externe Signatur, Offsite-Snapshot
- Secret- und Konfigurationsvalidierung beim Start
- Healthcheck, Readinesscheck und Doctor-Report
- strukturierte Logs, Fehlerdiagnose und Betriebswarnungen
- HTTP-API-Sicherheitsgrenzen, Body-Limits, Auth und sichere Defaults
- Deployment-Modus, Docker, persistente Pfade und Reverse-Proxy-Annahmen
- GitHub-Webhooks, Payload-Fixtures, Reconciliation und Fehlerfalltests
- E2E-Kernpfad, Integrationstests und Timeout-Isolation
- Migrationsfähigkeit und lokale Datenverlustannahmen
- Runtime-Tool-Guardrails und Generated-Artefakt-Integrität

## 6. Vorgehen

1. Bestimme den aktuellen Produktionsreife-Kontext aus `CURRENT_STATE.md`, aktiver Doku, Tests und Konfiguration.
2. Sammle 3 bis 7 realistische Kandidaten.
3. Bewerte jeden Kandidaten nach Risikoabbau, Betriebssicherheit, Blocker-Wirkung, Testbarkeit und Umsetzbarkeit.
4. Sortiere Kandidaten nicht nach Aufwand, sondern nach Produktionsreife-Gewinn pro kontrollierbarem Umsetzungsschritt.
5. Wähle genau einen Haupthebel.
6. Formuliere Akzeptanzkriterien, die nach Umsetzung beweisen, dass die Produktionsreife gestiegen ist.
7. Nenne bewusst unterlegene Alternativen, damit die Priorisierung nachvollziehbar ist.

## 7. Bewertungsheuristik

Ein guter Haupthebel erfüllt möglichst viele dieser Aussagen:

- Er reduziert ein Risiko, das im internen Betrieb real auftreten kann.
- Er macht Fehler schneller sichtbar oder Recovery sicherer.
- Er stärkt einen zentralen Pfad statt einer Randfunktion.
- Er ist mit Tests, Doctor-Checks, Scripts oder Dokumentation objektiv prüfbar.
- Er vermeidet einen großen, offenen Architekturumbau als ersten Schritt.
- Er baut auf vorhandenem Projektzustand auf und erzeugt keinen parallelen Ansatz.

Wenn zwei Kandidaten ähnlich stark sind, priorisiere denjenigen, der einen Betriebs- oder Datenintegritätsausfall besser verhindert.

## 8. Ergebnisformat

Verwende dieses Format:

```markdown
## Leverage-Prüfung

### Ergebnis
- Größter Hebel: ...
- Kurzfazit: ...
- Prüfumfang: ...

### Warum dieser Hebel Platz 1 ist
- Risikoabbau: ...
- Betriebssicherheit: ...
- Blocker-Wirkung: ...
- Testbarkeit: ...
- Umsetzbarkeit: ...

### Produktionsrisiko heute
- ...

### Konkrete nächste Arbeit
- ...

### Akzeptanzkriterien
- ...

### Unterlegene Alternativen
| Kandidat | Warum nicht Platz 1 |
| --- | --- |

### Nicht-Ziele
- ...

### Empfohlene Validierung
- ...
```

## 9. Statuslogik

- Wenn ein klarer Haupthebel existiert, benenne ihn auch bei unvollständiger Prüfung und markiere den Prüfumfang.
- Wenn die Quellen widersprüchlich sind, führe zuerst eine knappe Drift-Einschätzung durch und markiere die Empfehlung als vorläufig.
- Wenn der stärkste Hebel eine Altlast betrifft, verweise auf `legacy` für die Detailprüfung, aber entscheide trotzdem, ob er Produktionsreife am stärksten erhöht.

## 10. Zusammenspiel mit anderen Skills

- Nutze `drift`, wenn unklar ist, ob Status und Realität genug übereinstimmen, um sauber zu priorisieren.
- Nutze `legacy`, wenn der Haupthebel vermutlich im Entfernen alter Ansätze liegt.
- Nutze `sprint-workflow`, wenn aus dem Haupthebel ein konkreter Umsetzungssprint geplant oder ausgeführt werden soll.
