# Minimal Session Example

Connect to paper, fetch a quote, disconnect. No credentials required.

```bash
PYTHONPATH=src python examples/minimal_session/run.py
```

Equivalent CLI checks:

```bash
PYTHONPATH=src broker --broker paper verify
PYTHONPATH=src broker --broker paper doctor
```