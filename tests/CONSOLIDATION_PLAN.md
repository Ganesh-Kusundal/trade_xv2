# Test consolidation plan

Align tests with **source hierarchy** and the **test pyramid**.

## Target layout (current)

```text
tests/
├── unit/
│   ├── domain/                 ↔ src/domain/**
│   ├── brokers/{dhan,upstox,paper,common}/  ↔ src/brokers/**
│   ├── security/
│   └── property/
├── component/
│   ├── oms/                    ↔ src/application/oms/**
│   ├── execution|trading|…     ↔ src/application/**
│   └── runtime/                ↔ src/runtime/**
├── integration/
│   ├── api/                    ↔ src/interface/api/**
│   ├── brokers/{dhan,upstox}/  ↔ live/contract broker flows
│   ├── capability|quant|performance|scripts|contract/
│   └── …
├── e2e/ (+ scenarios, stability, stress)
├── chaos/
└── architecture/ (+ regression_invariants)
```

## Waves

| Wave | Scope | Status |
|------|--------|--------|
| **1** | Domain unit + OMS/execution/trading component | **done** |
| **2** | Fold leftover `tests/*` buckets; rehome broker package tests | **done** |
| **3** | Analytics / datalake / infrastructure / interface / config | **done** |
| **4** | Optional: rename residual history-ish names; CI matrix by layer | next |

## Mapping rule

| Source | Test home |
|--------|-----------|
| `src/domain/**` | `tests/unit/domain/**` |
| `src/application/oms/**` | `tests/component/oms/**` |
| `src/brokers/{id}/**` unit | `tests/unit/brokers/{id}/` |
| `src/brokers/{id}/**` integration | `tests/integration/brokers/{id}/` |
| `src/interface/api/**` | `tests/integration/api/` |
| Full stack | `tests/e2e/` |

**Do not add new tests under `src/**/tests`.**

## Run

```bash
PYTHONPATH=src pytest tests/unit -q
PYTHONPATH=src pytest tests/component -q
PYTHONPATH=src pytest tests/integration -q
PYTHONPATH=src pytest tests/e2e -q
PYTHONPATH=src pytest tests/architecture -q
```
