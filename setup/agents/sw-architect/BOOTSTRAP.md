# BOOTSTRAP
First run only:
1. Confirm this agent can read its local files and shared skills.
2. Run `nexusctl auth --output json` if a Nexus session is missing.
3. Run `nexusctl context --output json` to verify scoped visibility.
4. Report only missing prerequisites or successful readiness.

After successful bootstrap, do not repeat this ritual unless credentials, workspace, or agent identity changed.
