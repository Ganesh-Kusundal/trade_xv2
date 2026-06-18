# Import Direction Rules — Architectural Invariants

Enforces one-way dependency flow to prevent shotgun surgery and circular dependencies.

## Rules

1. **brokers.common** CANNOT import from brokers.dhan or brokers.upstox
2. **datalake** CANNOT import from cli
3. **analytics** CANNOT import from broker-specific adapters
4. **brokers.dhan** CANNOT import from brokers.upstox (and vice versa)

## Dependency Flow

```
cli → brokers → datalake → analytics
     ↕         ↕
  brokers.common (shared core)
```

## Violation Detection

Run these commands to check for violations:

```bash
# Check for broker imports in common
grep -r "from brokers.dhan" brokers/common/ --include="*.py"
grep -r "from brokers.upstox" brokers/common/ --include="*.py"

# Check for CLI imports in lower layers
grep -r "from cli" brokers/ datalake/ analytics/ --include="*.py"

# Check for cross-broker imports
grep -r "from brokers.dhan" brokers/upstox/ --include="*.py"
grep -r "from brokers.upstox" brokers/dhan/ --include="*.py"
```

## Exception Process

If you need to break these rules:

1. Document the reason in an ADR (`docs/adr/ADR-NNN-*.md`)
2. Add a `# noqa: import-direction` comment
3. Get approval from team lead

## Allowed Imports

✅ `cli` can import from `brokers.*`  
✅ `brokers/dhan` can import from `brokers.common.*`  
✅ `brokers/upstox` can import from `brokers.common.*`  
✅ `datalake` can import from `brokers.common.*`  
✅ `analytics` can import from `datalake.*`  

## Forbidden Imports

❌ `brokers.common` CANNOT import from `brokers.dhan` or `brokers.upstox`  
❌ `datalake` CANNOT import from `cli`  
❌ `analytics` CANNOT import from `brokers.dhan` or `brokers.upstox`  
❌ `brokers.dhan` CANNOT import from `brokers.upstox` (and vice versa)  
