# Test consolidation plan

Align tests with **source hierarchy** and the **test pyramid**.

## Target layout

```text
tests/
├── unit/                         # business rules only
│   ├── domain/                   # mirrors src/domain
│   │   ├── instruments/
│   │   ├── orders/
│   │   ├── ports/
│   │   ├── risk/
│   │   └── markets/
│   ├── security/
│   └── config/
├── component/                    # single service + fakes
│   ├── oms/                      # mirrors src/application/oms
│   ├── execution/
│   ├── trading/
│   ├── streaming/
│   └── composer/
├── integration/                  # multi-module collaboration
│   ├── brokers/
│   │   ├── dhan/
│   │   ├── upstox/
│   │   └── paper/
│   ├── persistence/
│   ├── messaging/
│   └── api/
├── e2e/                          # full process / paper / recovery
├── chaos/                        # failure injection
└── architecture/                 # import / layering / suite rules
```

## Mapping rule

| Source code | Test home |
|-------------|-----------|
| `src/domain/**` | `tests/unit/domain/**` |
| `src/application/oms/**` | `tests/component/oms/**` |
| `src/application/execution/**` | `tests/component/execution/**` |
| `src/application/trading/**` | `tests/component/trading/**` |
| `src/brokers/{id}/**` unit | `tests/unit/brokers/{id}/` *or keep contract near adapter until wave 3* |
| `src/brokers/{id}/**` integration | `tests/integration/brokers/{id}/` |
| `src/interface/api/**` | `tests/integration/api/` |
| Full stack | `tests/e2e/` |

**Stop growing** `src/**/tests` after each wave. Prefer new tests under `tests/`.

## Waves

| Wave | Scope | Status |
|------|--------|--------|
| **1** | Domain unit + OMS/execution/trading component | **this PR** |
| **2** | Fold `tests/{api,oms,contract,runtime}` into pyramid | next |
| **3** | Brokers package-local → `tests/unit|integration/brokers` | next |
| **4** | Analytics / datalake / infrastructure co-located → pyramid | next |
| **5** | Delete empty `src/**/tests`, enforce “no new package-local tests” in architecture | next |

## Behavioral naming (unchanged)

File names describe **guarantees**, not phases/tickets. Enforced by
`tests/architecture/test_test_suite_uses_behavioral_names.py`.

## Heuristic

> If I rewrite the implementation but keep the same external behavior, keep the test.

## Run

```bash
PYTHONPATH=src pytest tests/unit -q
PYTHONPATH=src pytest tests/component -q
PYTHONPATH=src pytest tests/integration -q
PYTHONPATH=src pytest tests/e2e -q
```
