## Summary

- What problem does this PR solve?
- What changed?

## Validation

- [ ] `dashboard`: `npm run lint`
- [ ] `dashboard`: `npm run typecheck`
- [ ] `dashboard`: `npm run test`
- [ ] `dashboard`: `npm run build`
- [ ] Service checks run where applicable

## Evidence

- Link issue(s):
- Screenshots/logs (if UI or behavior changed):

## Operational Notes

- New environment variables:
- Breaking changes:
- Deployment considerations:

## Audit Team Checklist

_Required for all PRs. See [`.github/AUDIT_TEAM.md`](.github/AUDIT_TEAM.md) for full criteria._

- [ ] Change is within scope of the active roadmap phase
- [ ] Risk/execution pipeline contract is unchanged or strengthened
- [ ] Signal explainability fields are present and correctly typed (if touching `services/signal/`)
- [ ] No secrets or hardcoded credentials introduced
- [ ] Dependencies reviewed for CVEs (if packages were added or upgraded)
- [ ] Health endpoints and readiness checks in place (if adding a new service)
- [ ] New env vars, ports, or schema migrations documented above and in `docs/ENVIRONMENT.md`
