---
name: trading_safety_monitoring
description: Monitor trading operational health, risk limits, and exchange/system status without executing trades.
---

# Trading Safety Monitoring

Check what is available and current:

- mode and live/paper state
- positions
- PnL and drawdown
- open order count
- risk limits
- exchange/system health
- anomaly indicators

Alert fields:

- severity: `critical`, `high`, `medium`, or `low`
- observed value
- threshold or expected range
- evidence timestamp
- recommended owner
- immediate safe next action

Never infer live risk from stale or missing data. Report uncertainty instead.
