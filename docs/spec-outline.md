# DocFlow – Full Architecture & Specification (v0.1)

## 1. Purpose and Scope

DocFlow is a modular, provider‑agnostic document intelligence toolkit for **schema‑driven extraction** using LLMs (initially Gemini).  
It is organized into three independent layers:

- **core** – extraction engine, schemas, profiles, provider abstraction  
- **sdk** – Python client + CLI for developers & agents  
- **service** – optional HTTP/PubSub façade for Cloud Run pipelines  

This spec defines:
- repository structure  
- responsibilities of each layer  
- configuration rules  
- package layout (`src/`)  
- extensibility for future providers and parsers  

## 2. Repository Layout (src-based)

```
docflow/
  pyproject.toml
  src/
    docflow/
      __init__.py
      core/
      sdk/
  service/
  tests/
  docs/
```

Only `src/docflow` is included in the installable package.  
`service/` lives in the repo but is **not packaged**.

## 3. Core Layer

### Responsibilities
- Schema parsing, normalization, validation  
- Profiles as reusable extraction configurations  
- Abstraction for LLM model providers  
- Orchestration of prompts, structured output, validation  
- Zero dependency on HTTP frameworks  
- Zero direct environment reads (config is injected)

### Structure
```
core/
  config.py
  errors.py
  models/
    schema_defs.py
    profiles.py
    documents.py
  providers/
    base.py
    gemini.py
  extraction/
    engine.py
    pipelines.py
  utils/
    logging.py
    io.py
```

## 4. SDK Layer

### Responsibilities
- Python client for local or remote mode  
- CLI (`docflow`)  
- Profile resolution from disk  
- Configuration management  
- Friendly errors and output

### Structure
```
sdk/
  config.py
  client.py
  profiles.py
  errors.py
  cli/
    main.py
```

### Modes
- `local`: uses core directly  
- `remote`: calls Cloud Run service via HTTP  

## 5. Service Layer

### Responsibilities
- Expose extraction engine over HTTP  
- Parse requests, materialize DocSources, call core  
- Optional Pub/Sub event handlers  
- Lives outside installable package

### Structure
```
service/
  config.py
  app.py
  handlers/
    http_extract.py
    events_pubsub.py
  dependencies.py
  requirements.txt
  Dockerfile
```

## 6. Packaging Strategy

`pyproject.toml` at repo root:

```
[project]
name = "docflow"
version = "0.1.0"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

This ensures only `src/docflow` is packaged.  
`service/` remains local code for Docker builds.

## 7. External Library Integration

External structured-output libs **may** be used inside providers:

- Instructor  
- Guardrails  
- LangExtract  

Integration happens **inside** `GeminiProvider` or future providers;  
DocFlow's public API remains unchanged.

## 8. CLI Commands (Initial)

```
docflow extract --input file.pdf --schema schema.json
docflow extract --all file.pdf
docflow describe file.pdf
docflow profiles list
docflow profiles show NAME
```

## 9. Python API

```
from docflow.sdk import DocflowClient
client = DocflowClient(mode="local")
result = client.extract(files=["a.pdf"], schema=my_schema)
```

Local = call core  
Remote = call service  

## 10. Future Extensions

- Additional providers  
- Document parsing integration (Docling)  
- Multi-step pipelines  
- Advanced exporters  
