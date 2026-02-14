# Contributing to TitanFlow

Thanks for contributing. This guide explains how to propose, implement, and validate changes so reviews stay fast and predictable.

## Ground Rules

- Keep PRs focused on one problem area.
- Prefer incremental changes over large multi-feature branches.
- Open an issue for architectural or cross-service changes before implementation.
- Update documentation whenever behavior, interfaces, or setup changes.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Node.js 20+
- Python 3.10+
- GitHub account with fork access

## Setup

1. Fork and clone.

```bash
git clone https://github.com/<your-username>/Titan-Finance-.git
cd Titan-Finance-
```

2. Configure environment.

```bash
cp .env.example .env
```

3. Start dependencies for end-to-end work.

```bash
docker compose up -d postgres questdb redis
```

4. Install project-specific dependencies when needed.

```bash
# dashboard
cd dashboard
npm install

# service example
cd ../services/signal
pip install -r requirements.txt
```

## Branching and Commits

- Branch from `main`.
- Branch naming:
  - `feat/<short-description>`
  - `fix/<short-description>`
  - `docs/<short-description>`
  - `chore/<short-description>`
- Use imperative commit messages with concise scope.

Examples:
- `feat(signal): publish top feature explanations`
- `fix(gateway): handle redis reconnect on startup`
- `docs(readme): add environment variable matrix`

## Coding Standards

### Python

- Target Python 3.10+.
- Follow PEP 8.
- Keep service entrypoints small; push logic into modules.
- Log operational failures with enough context for triage.

### TypeScript/React (Dashboard)

- Keep component files focused and composable.
- Prefer typed data models over untyped objects.
- Avoid silent runtime fallback behavior for critical UI states.

## Validation Requirements

Run the checks relevant to your change before opening a PR.

### Dashboard (`dashboard/`)

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

### Python services (`services/<service>/`)

```bash
pip install -r requirements.txt
flake8 .
python main.py
```

### Docker stack smoke check

```bash
docker compose up --build -d
docker compose ps
```

## Pull Request Expectations

Every PR should include:
- Problem statement and root cause.
- Summary of what changed.
- Validation evidence (commands and output summary).
- Related issues (`Closes #123` format when applicable).
- Screenshots or logs for UI/runtime behavior changes.
- Config or migration notes for new env vars, ports, or schemas.

## Review and Merge

- Address feedback with follow-up commits (avoid squashing during active review).
- Resolve conversations before requesting final approval.
- Keep discussion technical and implementation-specific.

## Security Reporting

Do not open public issues for vulnerabilities. Use GitHub Security Advisories for private disclosure.
