# Skill: Code — Code Analysis, Generation & Debugging

> For agents working with codebases, writing code, or debugging issues.

## When to Use

When reading, writing, modifying, or debugging code.

## Code Memory Protocol

### Save Code Snippets
```
Call: automem → memorize(
    content="```python\nThe function we just wrote\n```",
    mem_type="code_snippet",
    scope="domain",
    scope_id="PROJECT_NAME",
    importance=0.7,
    tags="language, component, feature"
)
```

### Save Bug Fixes
```
Call: automem → memorize(
    content="Bug: X happened because of Y. Fix: Z.",
    mem_type="bug_fix",
    scope="domain",
    scope_id="PROJECT_NAME",
    importance=0.9,
    tags="bug, component, root-cause"
)
```

### Save Configurations
```
Call: automem → memorize(
    content="Config setting: KEY=VALUE because REASON",
    mem_type="config",
    scope="domain",
    scope_id="PROJECT_NAME",
    importance=0.8,
    tags="config, component"
)
```

### Before Writing Code — Check Memory
```
1. vk-cache → request_context(query="How did we solve PROBLEM_TYPE before?")
2. engram-bridge → search_decisions(query="COMPONENT architecture")
3. If memory has patterns → reuse them
4. If not → design new solution and save it
```

### Error Traces
```
When an error occurs, save it:
automem → memorize(
    content="Error: TRACE\nContext: WHAT_WERE_WE_DOING\nFix: HOW_WE_FIXED_IT",
    mem_type="error_trace",
    scope="domain",
    importance=0.8,
    tags="error, component"
)
```

## Code Review Protocol

1. Check if similar code exists in memory
2. Review against saved decisions and patterns
3. Save any new decisions made during review
4. Update existing memories if they're outdated
