import sqlite3
import json
conn = sqlite3.connect('/opt/openclaw/state/nexusctl/nexusctl.sqlite3')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT handoff_id, objective, status, github_issue_ref FROM handoff_requests").fetchall()
print(json.dumps([dict(ix) for ix in rows], indent=2))
