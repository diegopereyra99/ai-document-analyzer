# docflow Profile Management Specification (v1)

## 1. Overview
A **profile** in *docflow* is a declarative recipe describing how the engine should perform a cognitive task such as extraction, description, or classification. Profiles allow users to reuse prompts, schemas, and instructions without rewriting configurations, and support project-level and global installations.

## 2. Profile Structure
Profiles are written in YAML. Each profile defines:

```yaml
id: string
mode: string
schema: string | null
prompt: string | null
system_instruction: string | null
params: {}
```

## 3. Field Definitions
- **id**: Unique profile name.
- **mode**: Cognitive task (e.g., extract, describe, classify).
- **schema**: Path to JSON schema (optional).
- **prompt**: Path to .txt file (optional).
- **system_instruction**: Path to .txt file (optional).
- **params**: Reserved for future extensibility.

## 4. Profile Locations
Profiles are resolved in priority order:
1. Project-local (`./.docflow/profiles/*.yaml`)
2. User-global (`~/.docflow/profiles/*.yaml`)
3. Built-in (`docflow/profiles/*.yaml`)

## 5. Built-in Profiles (examples)

### extract.yaml
```yaml
id: extract
mode: extract
schema: null
prompt: null
system_instruction: null
params: {}
```

### extract_all.yaml
```yaml
id: extract_all
mode: extract
schema: "./schemas/extract_all.json"
prompt: "./prompts/extract_all_prompt.txt"
system_instruction: "./system_instructions/extract_all_system.txt"
params: {}
```

### describe.yaml
```yaml
id: describe
mode: describe
schema: null
prompt: null
system_instruction: null
params: {}
```

### classify.yaml (optional)
```yaml
id: classify
mode: classify
schema: null
prompt: null
system_instruction: null
params: {}
```

## 6. Creating and Editing Profiles via CLI
```
docflow profile create my_profile --mode extract --schema schema.json
docflow profile edit my_profile
docflow run my_profile file.pdf
```

## 7. Runtime Resolution Steps
1. Load profile YAML.
2. Load mode defaults.
3. Apply overrides (prompt/system/schema).
4. Apply runtime overrides (CLI flags).
5. Build `ResolvedProfile` object.

## 8. Extensibility
`params` is reserved for future options such as verbosity, confidence, or enrichment—none of which are implemented in v1. This allows safe forward evolution without breaking existing profiles.
