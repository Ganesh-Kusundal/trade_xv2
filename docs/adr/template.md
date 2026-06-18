# ADR Template — Architecture Decision Record

**Instructions**: Copy this file to `docs/adr/ADR-NNN-short-title.md` and fill in each section.

---

# ADR-NNN: [Brief Title Describing the Decision]

**Status**: [Proposed | Accepted | Deprecated | Superseded by ADR-NNN]  
**Date**: YYYY-MM-DD  
**Authors**: [Name(s)]  
**Reviewers**: [Name(s)]  
**Labels**: [architecture | performance | security | broker | analytics | cli | datalake]

## Context

[Describe the problem, constraints, and forces at play. What is the issue that we're trying to address?]

[Include relevant background: current implementation, pain points, technical debt, performance metrics, or architectural concerns.]

## Decision

[Describe the decision that was made. What is the change that we're proposing?]

[Be specific about WHAT is changing and WHY this particular approach was chosen.]

## Consequences

[Describe the resulting context, after applying the decision. What becomes easier or more difficult?]

### Positive
- [List positive outcomes]
- [Improved maintainability, performance gains, reduced complexity, etc.]

### Negative
- [List negative outcomes or trade-offs]
- [Increased learning curve, temporary duplication, migration effort, etc.]

### Risks
- [Risk 1]: [Description and mitigation strategy]
- [Risk 2]: [Description and mitigation strategy]

## Alternatives Considered

### Alternative 1: [Name]
**Description**: [Brief description of the alternative approach]  
**Pros**: 
- [Advantage 1]
- [Advantage 2]

**Cons**: 
- [Disadvantage 1]
- [Disadvantage 2]

**Why Rejected**: [Specific reason this alternative was not chosen]

### Alternative 2: [Name]
**Description**: [Brief description]  
**Pros**: [...]  
**Cons**: [...]  
**Why Rejected**: [Reason]

## Implementation Notes

[Any specific implementation details, gotchas, or follow-up tasks]

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

## Related ADRs

- [ADR-NNN](./ADR-NNN-title.md) — [Relationship]
- [ADR-NNN](./ADR-NNN-title.md) — [Relationship]

## References

- [Link to related documentation, external resources, or code]
- [GitHub issue #NNN](https://github.com/.../issues/NNN)
- [Design document or spec]

---

**Review Checklist**:
- [ ] All affected modules identified
- [ ] Backward compatibility considered
- [ ] Test strategy defined
- [ ] Migration path documented (if applicable)
- [ ] Performance impact assessed
- [ ] Security implications reviewed
