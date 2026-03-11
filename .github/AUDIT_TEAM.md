# TitanFlow Audit Team Charter

This document defines the audit team's structure, responsibilities, goals, and review cadence for the TitanFlow algorithmic trading platform. Its purpose is to ensure that all code changes remain aligned with the project roadmap, quality standards, risk controls, and production readiness requirements.

---

## Mission

Maintain the integrity, security, and strategic alignment of TitanFlow by reviewing all significant changes against established standards — before they reach production.

---

## Team Structure

| Role | GitHub Team Slug | Scope |
|------|-----------------|-------|
| **Audit Lead** | `@jacattac314/audit-team` | All paths — overall alignment, governance, cross-cutting concerns |
| **Signal & ML Reviewers** | `@jacattac314/signal-ml-reviewers` | `services/signal/` — AI models, feature engineering, explainability, confidence scoring |
| **Risk & Compliance Reviewers** | `@jacattac314/risk-compliance-reviewers` | `services/risk/`, `services/execution/` — kill-switch logic, position limits, order lifecycle |
| **Infrastructure Reviewers** | `@jacattac314/infrastructure-reviewers` | Docker, CI/CD, database schemas, gateway service, environment configuration |
| **Dashboard Reviewers** | `@jacattac314/dashboard-reviewers` | `dashboard/` — UI accuracy, real-time data display, operational views |
| **Security Reviewers** | `@jacattac314/security-reviewers` | API keys, secrets handling, dependencies, OWASP top-10 surface area |

Code ownership paths are defined in [`CODEOWNERS`](../CODEOWNERS).

---

## Goals & Alignment Criteria

Every change reviewed by the audit team must be evaluated against these goals:

### 1. Roadmap Alignment
- Changes must support the active phase in [`ROADMAP.md`](../ROADMAP.md).
- Architectural or cross-service changes require a linked issue opened before implementation (per [`CONTRIBUTING.md`](../CONTRIBUTING.md)).
- Scope creep or features beyond the current phase exit criteria must be flagged.

### 2. Risk Control Integrity
- The `risk → execution` pipeline contract (payload schema, retries, idempotency) must never be weakened.
- Kill-switch logic must remain testable and deterministic.
- Position and portfolio limits per contender must be enforced and auditable.

### 3. Signal Explainability
- Every trade must be traceable to a model decision artifact (model ID, confidence score, top features).
- Explainability payloads must conform to the typed signal schema (`model_id`, confidence, explanation format).
- No silent fallback behavior that obscures the source of a trading signal.

### 4. Code Quality Standards
- **Python**: PEP 8 compliance, flake8 clean, service entrypoints kept small.
- **TypeScript/React**: Typed data models, no untyped critical state, composable components.
- All relevant CI checks must pass before merge: linting, type-checking, tests, Docker build.

### 5. Security Posture
- No API keys, secrets, or credentials committed to the repository.
- Dependencies reviewed for known CVEs on addition or upgrade.
- Environment variables follow the pattern in `.env.example` — no hardcoded values in service code.
- OWASP top-10 surface areas (injection, XSS, insecure deserialization) must be considered for any external-facing change.

### 6. Operational Readiness
- New services or significant changes must include a health endpoint and startup readiness check.
- Docker Compose changes must not break the `docker compose up --build` smoke test.
- Any new environment variables, ports, or schema migrations must be documented in the PR and in `docs/ENVIRONMENT.md`.

---

## Review Process

### Standard PR Review
1. Author opens a PR using the PR template and completes all checklist items.
2. CODEOWNERS triggers automatic review requests based on changed paths.
3. At least **one audit team member** must approve before merge.
4. For risk/execution or signal/ML changes: **one domain specialist** (Risk & Compliance or Signal & ML reviewer) must also approve.
5. All CI checks must be green. No bypassing CI with `--no-verify` or equivalent.

### Audit Finding
If a reviewer identifies a goal misalignment or quality issue:
1. Open an issue using the **Audit Finding** issue template (`.github/ISSUE_TEMPLATE/audit_finding.yml`).
2. Label the issue `audit-finding` and tag the relevant team.
3. Block merge until the finding is resolved or explicitly accepted with documented rationale.

### Escalation
- Disputes on audit findings escalate to the Audit Lead.
- Security findings of high or critical severity are handled via GitHub Security Advisories (not public issues).

---

## Review Cadence

| Activity | Frequency | Owner |
|----------|-----------|-------|
| PR reviews | Continuous (triggered by PR open/update) | Relevant CODEOWNERS |
| Roadmap alignment check | Start of each roadmap phase | Audit Lead |
| Dependency security scan | Monthly or on major version bumps | Security Reviewers |
| Test coverage review | Monthly — track against `docs/TEST_COVERAGE_ANALYSIS.md` | Audit Lead |
| CODEOWNERS & charter update | As team or project structure evolves | Audit Lead |

---

## Audit Checklist Reference

Use this checklist as a quick reference during reviews. The full criteria are in the Goals section above.

- [ ] Change is within scope of the active roadmap phase
- [ ] Risk/execution pipeline contract is unchanged or strengthened
- [ ] Signal explainability fields are present and correctly typed
- [ ] CI checks pass (lint, typecheck, tests, Docker build)
- [ ] No secrets or hardcoded credentials introduced
- [ ] Dependencies reviewed for new CVEs (if packages added/upgraded)
- [ ] Health endpoints and readiness checks in place for any new service
- [ ] New env vars, ports, or schema changes are documented
- [ ] PR template is fully completed by the author

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [`CODEOWNERS`](../CODEOWNERS) | Automatic review assignment by path |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Branching, commit, and PR standards |
| [`ROADMAP.md`](../ROADMAP.md) | Phase-by-phase implementation plan |
| [`SECURITY.md`](../SECURITY.md) | Vulnerability disclosure policy |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | System design and data flow |
| [`docs/TEST_COVERAGE_ANALYSIS.md`](../docs/TEST_COVERAGE_ANALYSIS.md) | Test coverage metrics and gaps |
| [`docs/OPERATIONS.md`](../docs/OPERATIONS.md) | Operational runbooks and incident response |
