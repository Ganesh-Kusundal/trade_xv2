# Qoder Feature Gap Analysis: /ultra-review and /ultra-plan

## Problem Statement

**Built-in Qoder GUI slash commands are NOT available in qodercli**

### Available in Qoder GUI ✅
- `/ultra-review` - Ultra-deep architecture review
- `/ultra-plan` - Comprehensive multi-phase planning
- Other built-in slash commands

### Available in qodercli ❌
- `/ultra-review` - **NOT AVAILABLE**
- `/ultra-plan` - **NOT AVAILABLE**
- Only project-level skills and agents are accessible

## Root Cause Analysis

### Architecture Difference

**Qoder GUI:**
- Full IDE integration
- Access to Qoder's internal command registry
- Built-in slash commands loaded from Qoder's core
- Direct access to proprietary features

**qodercli (v1.0.26):**
- Standalone CLI binary
- Limited to: agents, skills, hooks, plugins
- No access to GUI's internal slash command registry
- Missing feature parity with GUI

### Missing Components in CLI

1. **Internal Slash Command Registry**
   - GUI has built-in commands registered in Qoder's core
   - CLI doesn't load or expose these internal commands

2. **Mode Switching Protocol**
   - `/ultra-review` and `/ultra-plan` likely switch the AI into specific modes
   - CLI has `--agent` flag but no equivalent "mode" system

3. **Proprietary Features**
   - These commands may be Qoder Pro/Enterprise features
   - May not be intended for CLI access yet

## Current Workarounds

### Option 1: Use Agents Directly (Partial Solution)
```bash
# Instead of /ultra-review
qodercli --agent architecture-reviewer "Perform ultra-deep 9-phase architecture audit"

# Instead of /ultra-plan
qodercli --agent quant-platform-orchestrator "Create master remediation plan"
```

**Limitations:**
- Loses the "mode switching" behavior
- Doesn't trigger the exact same workflow
- Missing GUI-specific enhancements

### Option 2: Create Wrapper Skills (What We Did)
Created custom skills in `.qoder/skills/`:
- `ultra-review/SKILL.md`
- `ultra-plan/SKILL.md`

**Advantages:**
- Available as `/ultra-review` and `/ultra-plan` in CLI
- Can customize behavior
- Works with existing agent system

**Limitations:**
- Not the "raw" Qoder implementation
- May miss proprietary features
- Wrapper, not native implementation

## Feature Parity Gap

| Feature | Qoder GUI | qodercli | Gap |
|---------|-----------|----------|-----|
| `/ultra-review` | ✅ Built-in | ❌ Missing | 🔴 Critical |
| `/ultra-plan` | ✅ Built-in | ❌ Missing | 🔴 Critical |
| Custom agents | ✅ | ✅ | ✅ Parity |
| Custom skills | ✅ | ✅ | ✅ Parity |
| Mode switching | ✅ | ❌ | 🟠 High |
| Internal commands | ✅ | ❌ | 🟠 High |

## Recommended Solutions

### Short-term (Available Now)
✅ **Use wrapper skills** (already created)
- Located in `.qoder/skills/ultra-review/SKILL.md`
- Located in `.qoder/skills/ultra-plan/SKILL.md`
- Accessible via `/ultra-review` and `/ultra-plan` in CLI

### Medium-term (Request from Qoder)
🔶 **Feature Request to Qoder Team**
- Request CLI parity for built-in slash commands
- Propose `--mode` flag: `qodercli --mode ultra-review`
- Request internal command registry exposure

### Long-term (Architecture Change)
🔷 **Qoder CLI Enhancement**
- Add support for internal slash commands
- Implement mode switching protocol
- Sync command registry between GUI and CLI

## Testing Wrapper Skills

### Test ultra-review
```bash
qodercli skills list | grep ultra-review
qodercli -p "/ultra-review Perform architecture audit on /api directory"
```

### Test ultra-plan
```bash
qodercli skills list | grep ultra-plan
qodercli -p "/ultra-plan Create plan for OMS refactoring"
```

## Conclusion

The `/ultra-review` and `/ultra-plan` commands are **Qoder GUI-exclusive built-in features** not yet exposed in qodercli. 

**Current best solution:** Use the wrapper skills created in `.qoder/skills/` which provide similar functionality by invoking the appropriate agents with enhanced prompts.

**To get native CLI support:** Submit a feature request to Qoder for slash command parity between GUI and CLI.
