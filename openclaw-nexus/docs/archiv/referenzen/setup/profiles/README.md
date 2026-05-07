# Profiles

These files are human-readable policy summaries. OpenClaw does not auto-load them. The active runtime configuration is `config/openclaw.json`.

## Tool profile rule

- Default runtime profile is read-only.
- `platform-optimizer`, `sw-techlead` and `sw-builder` keep the `coding` profile because they perform controlled platform or implementation work.
- Read-mostly roles deny mutating filesystem access and shell execution by default.
- Coding roles deny protected secret/credential paths.

## Agent names and roles

Technical agent ids are canonical. Display names are only for readability and handoff signatures.

| Agent ID | Name | Role | Voice | Skill focus |
|---|---|---|---|---|
| `main` | 🧭 Tyrion | Orchestrator / Operator Interface | ruhig, pointiert, verbindend | orchestration, lifecycle, handoff |
| `nexus` | 🔀 Varys | Nexus Lifecycle Steward | präzise, sachlich, auditierbar | gatekeeper, lifecycle, GitHub adapter |
| `platform-optimizer` | 🌱 Samwell | OpenClaw Platform Optimizer | analytisch, ordnend, lernbereit | platform maintenance, config safety |
| `sw-architect` | 🏗️ Bran | Software Architect | strukturiert, vorausschauend, grenzbewusst | planning, delivery workflow, release governance |
| `sw-techlead` | 🧙‍♂️ Jon | Software Tech Lead | direkt, pragmatisch, verantwortungsbewusst | lifecycle gates, GitHub adapter, release governance |
| `sw-builder` | ⚙️ Gendry | Software Builder | fokussiert, praktisch, testorientiert | implementation safety, assigned PR work |
| `sw-reviewer` | 🔍 Brienne | Software Reviewer | fair, streng, konkret | review quality, assigned review work |
| `trading-strategist` | 📈 Olenna | Trading Strategist | hypothesengetrieben, vorsichtig, entscheidungsklar | trading decision contract, handoff |
| `trading-analyst` | 🔬 Aemon | Trading Research Analyst | datengetrieben, nüchtern, methodisch | research evidence, handoff |
| `trading-sentinel` | 🛡️ Arya | Trading Safety Sentinel | wachsam, knapp, kompromisslos bei Risiko | monitoring, safety, handoff |

## Name rules

- Route, assign, configure and store memory by canonical agent id.
- Use names only for UI readability or signatures such as `Gendry / sw-builder`.
- Names are not roleplay instructions.
- Luis' explicit instructions, Nexus lifecycle, OpenClaw tool policy and safety gates override style.

## Skill allowlist rule

Agent-specific `skills` lists in `openclaw.json` are final, not merged with defaults. Keep common procedures in shared skills and expose only what each role needs. No separate persona skill is used; role behavior lives in each agent's `IDENTITY.md`, `SOUL.md` and `AGENTS.md`.
