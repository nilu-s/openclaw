# Target-Version-Policy

Stand: 2026-05-05

Diese Policy beschreibt den Zielversions-Contract von OpenClaw Nexus. Sie trennt alte Kompatibilitätsversprechen von aktuellen Kontrollfeatures, damit Legacy-Pfade entfernt werden können, ohne operative Sicherheits- und Governance-Funktionen zu verlieren.

## Grundsatz

OpenClaw Nexus unterstützt genau eine aktuelle Zielversion. Maßgeblich sind das Nexusctl-Domänenmodell, die aktiven `nexus/*.yml`-Konfigurationen, die App-Services, die Adaptergrenzen, die fachlich benannten Tests und die aus Nexusctl generierten OpenClaw-Artefakte.

Historische Dateien, alte Imports, alte CLI-Kommandos, frühere Paketlayouts und archivierte Reports dürfen als Nachvollziehbarkeit im Archiv liegen. Sie sind aber keine Runtime-Quelle, kein Test-Contract und kein öffentlich unterstützter Produktpfad.

## Definition: Legacy-Kompatibilität

**Legacy-Kompatibilität** ist ein Mechanismus, der nur existiert, damit ein früherer Projektstand, ein altes Paketlayout, ein alter Command-Name, ein alter Importpfad oder ein historischer Report weiterhin wie ein aktueller Contract behandelt wird.

Legacy-Kompatibilität darf entfernt werden, wenn sie nicht mehr für die aktuelle Zielversion benötigt wird. Beispiele sind Rückwärtskompatibilitäts-Aliase, alte CLI-Kommandos, Migrationsservices ohne aktiven Produktauftrag und Tests, die historische Migrationspfade als Pflichtbestand erzwingen.

## Definition: Kontrollfeature

Ein **Kontrollfeature** ist ein aktueller Mechanismus zur Sicherheit, Integrität, Nachvollziehbarkeit oder Governance der Zielversion. Kontrollfeatures bleiben erhalten, auch wenn ihre Namen Begriffe wie `drift`, `reconcile`, `doctor`, `check`, `audit`, `policy` oder `stale` enthalten.

Kontrollfeatures dürfen verbessert, eindeutiger benannt und stärker getestet werden. Sie dürfen nicht entfernt werden, nur weil sie ältere Zustände erkennen, Drift melden oder historische Ereignisse auditierbar machen.

## Nicht mehr unterstützt

Die folgenden Pfade und Contracts gehören nicht zur Zielversion und werden nicht mehr als öffentliche oder aktive Produktoberfläche unterstützt:

- `legacy-import` CLI
- `LegacyImportService` als aktiver App-Service
- `referenzen/setup` als Runtime- oder Testquelle
- `AGENT_ALIASES` für alte Agentnamen
- `COMMAND_CAPABILITY_MAP` für alte Commands
- Backwards-compatible HTTP aliases
- Legacy-Import-Reports als aktive Entscheidungsquelle
- Tests, die Legacy-Import als Pflichtvertrag absichern

## Weiterhin unterstützt

Die folgenden Kontrollfeatures gehören ausdrücklich zur Zielversion und bleiben erhalten:

- Generated Artifact Drift Detection
- GitHub Projection Drift Detection
- Schedule/Runtime Drift Checks
- Merge Staleness Gates
- Reconciliation Alerts
- Audit Events
- Policy Gates
- Doctor Output als Zielversions-Contract

## Entscheidungsregel

Bei jedem Fund eines historischen Pfads gilt diese Frage:

```text
Ist das ein altes Kompatibilitätsversprechen oder ein aktuelles Kontrollfeature?
```

Entscheidung:

```text
Altes Kompatibilitätsversprechen: entfernen oder archivieren.
Aktuelles Kontrollfeature: behalten, sauber benennen und als Zielversions-Contract testen.
```

## Umgang mit Archivmaterial

Archivmaterial unter `docs/archiv/` darf fachliche Hintergründe erklären. Es darf aber nicht von Runtime-Code, aktiven Tests, Projektvalidierung oder generierten Zielartefakten geladen werden.

Wenn ein historisches Dokument eine weiterhin nützliche fachliche Idee enthält, wird diese Idee in die Zielstruktur übernommen. Der historische Pfad selbst bleibt dadurch nicht unterstützt.
