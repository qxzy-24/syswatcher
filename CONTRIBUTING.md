# Contributing to Syswatcher

Thank you for your interest in improving Syswatcher.

## Development Setup

1. Fork and clone the repository.
2. Create a virtual environment.
3. Install dependencies.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Workflow

1. Create a feature branch from `main`.
2. Make focused, minimal changes.
3. Keep commits descriptive and atomic.
4. Update documentation when behavior changes.
5. Open a pull request with clear context and validation notes.

## Quality Guidelines

- Keep the daemon resilient and restart-safe.
- Prefer backward-compatible config changes.
- Include defensive error handling around network and I/O.
- Do not commit secrets or environment-specific credentials.

## Pull Request Checklist

- [ ] Code compiles and runs locally
- [ ] `README.md` updated if needed
- [ ] Config changes documented
- [ ] No real tokens/credentials committed
- [ ] Changelog entry added when appropriate
