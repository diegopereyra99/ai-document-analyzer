# DocFlow

DocFlow is a provider-agnostic toolkit for schema-driven document extraction. It ships with a core engine, Python SDK + CLI, and an optional HTTP service for remote execution. Everything is profile-driven: a profile bundles schema + prompt + system instruction + provider options so you can reproduce extractions without re-specifying inputs.

## Vision and goals
- Always return structured output (JSON) defined by a schema, even for “schema-less” user modes (e.g., `describe`, `extract_all` ship with fixed schemas).
- Minimal prompt text; schemas are passed via structured-output to providers. Document bytes/URIs are attached, not inlined in prompts.
- Provider-agnostic core; Gemini is the first provider.
- Profiles live as files (bundled built-ins + project/user overrides) for reproducibility and shareability.

## Layout
- `src/docflow/core`: engine, schemas, providers, documents, errors, config
- `src/docflow/sdk`: client, CLI, profile loader
- `src/docflow/sdk/builtin_profiles`: built-in profile definitions (YAML) plus prompts/system instructions and schemas
- `service/`: optional HTTP façade (FastAPI)
- `tests/`: unit tests

## Profiles
- Bundled built-ins under `src/docflow/sdk/builtin_profiles/`:
- `extract`: schema-driven extraction (user supplies schema)
- `extract_all`: broad Spanish schema with prompts/instructions to extract as much as possible
- `describe`: fixed schema for document type + summary
- Profile format (YAML/JSON):
  - `id`, `mode` (`extract|describe|classify`), optional `schema` (path or inline), optional `prompt`, optional `system_instruction`, optional `multi_doc_behavior` (default `per_file`), optional `params`. Profiles like `extract_all` are specific recipes using `mode=extract`.
  - Resolution order: project `.docflow/profiles` → user `~/.docflow/profiles` → bundled built-ins.
  - See `docflow_profile_spec_v1.md` for details.

## Development

```bash
pip install -e .
pytest
```

Use `docflow --help` for CLI usage.
