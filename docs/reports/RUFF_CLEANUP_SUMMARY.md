# Ruff Cleanup Summary

## ✅ Completed Tasks

### 1. Fixed All 14 Undefined Name Bugs (F821)

All undefined name errors have been resolved:

| File | Issue | Fix Applied |
|------|-------|-------------|
| `brokers/dhan/depth_20.py` | `asyncio` undefined | Added `import asyncio` |
| `brokers/dhan/depth_200.py` | `asyncio` undefined | Added `import asyncio` |
| `brokers/paper/paper_gateway.py` | `Position` undefined | Added `Position` to imports |
| `brokers/upstox/gateway.py` | `Quote` undefined | Added `Quote` to imports |
| `datalake/gateway.py` | `Quote`, `MarketDepth` undefined | Added both to imports |
| `datalake/journal.py` | `logger` undefined | Added `import logging` and `logger = logging.getLogger(__name__)` |
| `datalake/validation.py` | `Path` undefined | Added `from pathlib import Path` |
| `datalake/tests/test_validation.py` | `Path` undefined | Added `from pathlib import Path` |
| `tests/integration/test_event_replay_determinism.py` | `ProcessedTradeRepository` undefined | Added to imports |

**Verification:** ✅ `ruff check . --select=F821` now passes with "All checks passed!"

### 2. Created Automated Cleanup Script

**File:** `scripts/cleanup_unused_imports.py`

**Features:**
- Detects all 327 unused imports across 148 files
- Categorizes issues by type:
  - **Production code:** 123 issues in 61 files (safe to auto-fix)
  - **Test code:** 175 issues in 76 files (safe to auto-fix)
  - **Scripts:** 0 issues (would require manual review)
  - **Temp/refactor:** 29 issues in 11 files (manual review recommended)
- Generates detailed reports with:
  - Category summary
  - Top 10 files with most issues
  - Detailed file-by-file listing
  - Actionable recommendations

**Usage:**
```bash
# Show statistics only
python scripts/cleanup_unused_imports.py --stats

# Generate detailed report (dry run)
python scripts/cleanup_unused_imports.py

# Auto-fix safe unused imports
python scripts/cleanup_unused_imports.py --fix

# Or use ruff directly
ruff check . --fix --select=F401
```

## 📊 Current Ruff Status

### Before Cleanup:
- **Total issues:** 3,067
- **Undefined names (F821):** 14
- **Unused imports (F401):** 327

### After Cleanup:
- **Total issues:** ~1,596 (48% reduction from auto-fixes)
- **Undefined names (F821):** 0 ✅ (100% fixed)
- **Unused imports (F401):** 327 (ready for auto-fix)

## 🧪 Test Results

**Test Suite Status:** ✅ 149/150 tests passing (99.3%)

- No breaking changes introduced
- All undefined name fixes verified
- 1 pre-existing test failure (unrelated to ruff fixes)

## 🎯 Next Steps

### Immediate (Safe to Execute):
```bash
# Auto-fix remaining 327 unused imports
ruff check . --fix --select=F401

# Verify no breaking changes
python -m pytest tests/ --ignore=tests/performance -q
```

### Manual Review Required:
1. **Security Issues (149 total):**
   - 107 hardcoded passwords in function args (S106)
   - 42 hardcoded password strings (S105)
   - **Action:** Move to environment variables

2. **Code Quality (139 total):**
   - 60 try-except-pass blocks (S110)
   - 40 mutable class defaults (RUF012)
   - 37 imports not at top of file (E402)
   - 14 undefined names ✅ FIXED
   - **Action:** Review and fix case-by-case

3. **Logging Best Practices (53 total):**
   - 53 logging f-strings (G004)
   - **Action:** Convert to lazy logging format

### Files Requiring Special Attention:
- `temp/` directory (29 unused imports) - Consider deleting if no longer needed
- `temp_refactor/` directory - Likely obsolete refactoring artifacts
- Complex files with 7+ unused imports (see script output for top 10)

## 📝 Script Output Example

```
================================================================================
UNUSED IMPORTS CLEANUP REPORT
================================================================================

Total unused imports: 327
Files affected: 148

--------------------------------------------------------------------------------
CATEGORY SUMMARY
--------------------------------------------------------------------------------

PRODUCTION: 123 issues in 61 files
  ✓ Safe to auto-fix

TESTS: 175 issues in 76 files
  ✓ Safe to auto-fix

SCRIPTS: 0 issues in 0 files
  ⚠ Manual review recommended

TEMP: 29 issues in 11 files
  ⚠ Manual review recommended
```

## 🔍 Verification Commands

```bash
# Check for undefined names (should pass)
ruff check . --select=F821

# Check for unused imports
ruff check . --select=F401 --statistics

# Run full ruff check
ruff check . --statistics

# Run tests
python -m pytest tests/ --ignore=tests/performance -q
```

## 📌 Important Notes

1. **Circular Import Prevention:** The `brokers/common/core/domain.py` file had its import order reverted to prevent circular imports. Do NOT run `ruff check --fix --select=I001` on this file.

2. **Safe Auto-Fixes Applied:**
   - Import sorting (I001) - except domain.py
   - PEP 604 union annotations (UP007)
   - Blank line whitespace (W293)
   - Deprecated imports (UP035, UP037)
   - And 20+ other rule categories

3. **Manual Intervention Required:**
   - Hardcoded passwords (security critical)
   - Temp/refactor directories (may be obsolete)
   - Complex import dependencies

---

**Generated:** 2026-06-16
**Tools Used:** ruff 0.x, pytest 7.x
**Status:** ✅ Undefined names fixed, cleanup script created
