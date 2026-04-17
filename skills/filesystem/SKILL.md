# Skill: Filesystem — File Operations & Project Navigation

> For agents that need to read, write, or navigate files.

## When to Use

When working with files, directories, or navigating a project structure.

## File System Memory Protocol

### Track Important Files
```
When you read or write a significant file:
automem → memorize(
    content="File: path/to/file.py\nPurpose: What it does\nKey: Important details",
    mem_type="config",
    scope="domain",
    scope_id="PROJECT_NAME",
    importance=0.5,
    tags="file, component"
)
```

### Track Project Structure
```
When you discover project layout:
automem → memorize(
    content="Project structure: src/main.py, src/utils/, tests/",
    mem_type="fact",
    scope="domain",
    scope_id="PROJECT_NAME",
    importance=0.6,
    tags="structure, navigation"
)
```

### Before Modifying Files — Check Memory
```
1. vk-cache → request_context(query="What do I know about FILE or COMPONENT?")
2. Check if there are saved decisions about this file
3. Check if there's a reason the file is structured a certain way
```

## Rules

1. **Never modify files without understanding them first** — check memory
2. **Save structural decisions** — why a file exists matters
3. **Track config changes** — especially environment variables
4. **Note file relationships** — A imports B because C
