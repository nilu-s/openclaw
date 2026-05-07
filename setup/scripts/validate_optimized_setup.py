#!/usr/bin/env python3
import json, sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
json.load(open(root / 'config' / 'openclaw.json', encoding='utf-8'))

required_skills = set()
config = json.load(open(root / 'config' / 'openclaw.json', encoding='utf-8'))
required_skills.update(config.get('agents', {}).get('defaults', {}).get('skills', []))
for agent in config.get('agents', {}).get('list', []):
    required_skills.update(agent.get('skills', []))

missing = [s for s in sorted(required_skills) if not (root / 'skills' / s / 'SKILL.md').exists()]
if missing:
    raise SystemExit(f'Missing skills: {missing}')

banned = [
    'trading_goals_ref',
    'nexusctl handoff set-issue',
    'request set-issue',
    'gh issue create',
    'agent_persona_contract',
    'alias:',
]
violations = []
for folder in ['agents', 'skills']:
    for p in (root / folder).rglob('*.md'):
        text = p.read_text(encoding='utf-8')
        for b in banned:
            if b in text:
                violations.append(f'{p.relative_to(root)} contains legacy term: {b}')

if violations:
    raise SystemExit('\n'.join(violations))

print('OK: config JSON valid, skills present, no legacy/persona-contract terms in agents/skills.')
