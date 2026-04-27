# nexusctl API Contract (MVP)

Implementierte Backend-Erwartung fuer die Python-CLI.

## Endpunkte

1. `POST /v1/nexus/auth`
2. `GET /v1/nexus/capabilities`
3. `GET /v1/nexus/capabilities/{capability_id}`
4. `POST /v1/nexus/capabilities/{capability_id}/status`

## Header

- Folgeaufrufe senden `X-Nexus-Session-Id`
- Optional: `X-Nexus-Agent-Id`

## Request DTOs

### Auth

```json
{
  "agent_token": "tok_xxx",
  "domain": "Trading"
}
```

### Set Status

```json
{
  "to": "available",
  "reason": "All requirements verified and evidence linked."
}
```

## Fehlerbehandlung

Backend kann `error_code` + `message` liefern. Die CLI mappt auf:

- `NX-VAL-001`, `NX-VAL-002` -> Exit `2`
- `NX-NOTFOUND-001` -> Exit `3`
- `NX-PERM-001` -> Exit `4`
- `NX-PRECONDITION-001|002|003` -> Exit `6`
- `NX-INFRA-001|002` -> Exit `10`
