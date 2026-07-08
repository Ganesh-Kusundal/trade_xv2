---
name: graphify
description: >
  Code knowledge graph navigation and maintenance using the graphify CLI tool.
  Use BEFORE exploring the codebase with Read/Grep/Glob for any architecture,
  dependency, or code-relationship question. Triggers: "graphify", "show
  dependencies", "what depends on", "how does X connect", "find path between",
  "what's affected by", "code graph", "knowledge graph", "explore architecture",
  "understand module relationships", or any question about how parts of the
  codebase connect. Also use when starting any task that requires understanding
  cross-file dependencies, call chains, or module boundaries. Do NOT use for
  simple single-file edits where the target file is already known.
argument-hint: "<question or command>"
---

# Graphify — Code Knowledge Graph

You have access to a pre-built code knowledge graph at `graphify-out/`. This
graph captures AST-level and semantic relationships across the entire codebase —
including cross-file dependencies and inferred edges that grep/Read cannot find.

## Mandatory Orientation Rule

**Before using Read, Grep, or Glob to explore the codebase, run graphify first.**
This applies to you and every subagent you spawn. Include this rule explicitly
in every subagent prompt that involves code exploration.

Only skip graphify when:
1. You already know the exact file and lines to modify (e.g. from a prior query)
2. `graphify-out/graph.json` does not exist yet

## Quick Reference

### Navigation Commands

| Command | When to Use |
|---|---|
| `graphify query "<question>"` | Any codebase or architecture question — returns scoped subgraph |
| `graphify path "<A>" "<B>"` | Find dependency path between two symbols |
| `graphify explain "<concept>"` | All nodes related to a concept + plain-language explanation |
| `graphify affected "<X>"` | Reverse traversal — what breaks if X changes |

### Query Options

```
graphify query "<question>" --budget 4000    # cap output tokens (default 2000)
graphify query "<question>" --dfs            # depth-first instead of breadth-first
graphify query "<question>" --context R      # filter by edge relation (repeatable)
graphify affected "<X>" --depth 3            # deeper reverse traversal (default 2)
graphify affected "<X>" --relation imports   # filter by specific relation type
```

### Maintenance Commands

| Command | When to Use |
|---|---|
| `graphify update .` | After modifying code files — AST-only, no API cost |
| `graphify update . --force` | After large refactors that delete many files |
| `graphify check-update .` | Cron-safe check if graph is stale |
| `graphify cluster-only .` | Rerun community detection + regenerate report |
| `graphify label . --missing-only` | Name any unlabeled communities via LLM |

### Diagnostic Commands

| Command | When to Use |
|---|---|
| `graphify diagnose multigraph` | Report edge collapse risks / duplicate endpoints |
| `graphify tree` | Generate D3 collapsible-tree HTML visualization |
| `graphify benchmark` | Measure token reduction vs naive full-corpus approach |

### Memory & Feedback Loop

```
graphify save-result --question "Q" --answer "A" --outcome useful --nodes N1 N2
graphify reflect    # aggregate outcomes into LESSONS.md
```

## Workflow Patterns

### Pattern 1: Orient Before Exploring
```
graphify query "how does order execution work"
# → read the returned subgraph nodes with Read for detail
```

### Pattern 2: Impact Analysis Before Refactoring
```
graphify explain "BrokerGateway"
graphify affected "BrokerGateway" --depth 3
# → understand blast radius before making changes
```

### Pattern 3: Dependency Path Discovery
```
graphify path "DhanHttpClient" "OrderManager"
# → understand the coupling chain between two components
```

### Pattern 4: Post-Change Graph Sync
```
# After editing code files:
graphify update .
# AST-only, no LLM cost, keeps graph current
```

## Reading the Report

For broad architecture overview (when query/path/explain don't provide enough):
- Read `graphify-out/GRAPH_REPORT.md` — community hubs, extraction stats, corpus info
- Read `graphify-out/GRAPH_TREE.html` — interactive D3 tree visualization (run `graphify tree` first)

## Subagent Instruction Template

When spawning subagents for code exploration, include this in their prompt:

> Before using Read/Grep/Glob, orient yourself with graphify:
> - `graphify query "<your question>"` for scoped subgraph
> - `graphify path "<A>" "<B>"` for dependency paths
> - `graphify explain "<concept>"` for concept neighborhood
> Only use Read/Grep after graphify has oriented you and you need specific lines.
