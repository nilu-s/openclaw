# Skill Allowlists

Agent-specific `skills` lists in `openclaw.json` are final, not merged with defaults. Keep common procedures in shared skills and expose only what each role needs.

- Tyrion / main: orchestration + lifecycle + handoff contract
- Varys / nexus: gatekeeper + lifecycle + GitHub adapter
- Bran/Jon/Gendry/Brienne: software workflow with role-specific safety/review/release skills
- Olenna/Aemon/Arya: trading decision, research, and monitoring skills
- Samwell / platform-optimizer: platform maintenance + config safety

No separate persona skill is used. Names and task-specific behavior live in each agent's `IDENTITY.md` and `SOUL.md`.
