# nexusctl API Contract (MVP)

Implementierte Backend-Erwartung fuer die Python-CLI.

## Endpunkte

1. `POST /v1/nexus/auth`
2. `GET /v1/nexus/capabilities`
3. `GET /v1/nexus/capabilities/{capability_id}`
4. `POST /v1/nexus/capabilities/{capability_id}/status`
5. `POST /v1/nexus/handoffs`
6. `GET /v1/nexus/handoffs`
7. `POST /v1/nexus/handoffs/{handoff_id}/issue`

## Header

- Folgeaufrufe senden `X-Nexus-Session-Id`
- Optional: `X-Nexus-Agent-Id`

## Request DTOs

### Auth

```json
{
  "agent_token": "tok_xxx"
}
```

### Set Status

```json
{
  "to": "available",
  "reason": "All requirements verified and evidence linked."
}
```

### Handoff Submit

```json
{
  "objective": "Reduce reaction latency for risk-limit breaches.",
  "missing_capability": "Automatic hard-stop trigger when risk threshold is exceeded.",
  "business_impact": "Prevents prolonged exposure during volatility spikes.",
  "expected_behavior": "System halts new entries within breach window.",
  "acceptance_criteria": [
    "Given threshold breach, new entries are blocked within 500ms."
  ],
  "risk_class": "high",
  "priority": "P1",
  "trading_goals_ref": "trading-goal://risk/limit-hard-stop"
}
```

### Handoff Issue Link

```json
{
  "issue_ref": "issue://github/owner/repo#42",
  "issue_number": 42,
  "issue_url": "https://github.com/owner/repo/issues/42"
}
```

## Fehlerbehandlung

Backend kann `error_code` + `message` liefern. Die CLI mappt auf:

- `NX-VAL-001`, `NX-VAL-002` -> Exit `2`
- `NX-NOTFOUND-001` -> Exit `3`
- `NX-PERM-001` -> Exit `4`
- `NX-PRECONDITION-001|002|003` -> Exit `6`
- `NX-INFRA-001|002` -> Exit `10`
