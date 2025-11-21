# DocFlow – Detailed Architecture & Specification (v0.2)

## 1. Purpose and Scope

DocFlow is a modular, provider‑agnostic document intelligence toolkit for **schema‑driven extraction** from business documents (e.g. invoices, delivery notes) using LLMs (initially Gemini on Google Cloud).

DocFlow is split into three layers:

- **core** – extraction engine, schemas, profiles, provider abstraction
- **sdk** – Python client and CLI for developers, scripts, and agents
- **service** – optional HTTP/Pub/Sub façade for Cloud Run and event‑driven pipelines

This document specifies:

- repository and packaging layout
- responsibilities and public surface of each layer
- configuration rules (who reads env vars, who doesn’t)
- profile system (built‑in + user‑defined)
- CLI behavior and multi‑document handling
- extensibility strategy (providers, parsers, pipelines)
- guidelines for using external structured‑output libraries


## 2. Repository Layout and Packaging

DocFlow uses a modern `src/` layout. Only the `docflow` package is installed; the `service` folder is for deployment only.

```text
docflow/
  pyproject.toml
  src/
    docflow/
      __init__.py
      core/
        ...
      sdk/
        ...
  service/
    app.py
    ...
  tests/
    ...
  docs/
    ...
```

### 2.1 Installable Package

- Package name: **`docflow`**
- Installable via:

  ```bash
  pip install docflow  # from PyPI or Artifact Registry
  ```

- Public modules (intended for consumers):

  - `docflow.sdk` – main entrypoint (client + CLI)
  - `docflow.core` – lower‑level engine (for internal use, agents, advanced users)

### 2.2 `pyproject.toml` (minimal sketch)

```toml
[project]
name = "docflow"
version = "0.1.0"
description = "Schema-driven document extraction toolkit"
requires-python = ">=3.10"
dependencies = [
  "google-cloud-aiplatform",  # Gemini/Vertex
  # add pydantic/typer/etc. as needed
]

[project.scripts]
docflow = "docflow.sdk.cli.main:app"  # or equivalent

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

- This ensures only `src/docflow` ends up in the wheel.
- `service/` is *not* packaged; it imports `docflow` during container build.


## 3. Core Layer (`docflow.core`)

### 3.1 Responsibilities

The **core** is the engine. It:

- defines internal representations for:
  - schemas (fields, records, constraints)
  - profiles (named extraction configurations)
  - documents (sources such as file paths, GCS URIs, raw text)
- abstracts the LLM backend behind a **provider interface**
- orchestrates the extraction flow:
  - build prompts from schema/profile
  - call the provider to get structured output
  - validate and normalize the result

The core **must not**:

- depend on HTTP frameworks (FastAPI, Flask, etc.)
- read environment variables directly

Config and environment‑specific details are injected from outside (SDK, service, or agents).

### 3.2 Structure

```text
docflow/core/
  __init__.py
  config.py
  errors.py
  models/
    __init__.py
    schema_defs.py
    profiles.py
    documents.py
  providers/
    __init__.py
    base.py
    gemini.py
  extraction/
    __init__.py
    engine.py
    pipelines.py   # optional / future
  utils/
    __init__.py
    logging.py
    io.py
```

### 3.3 Core Components

#### 3.3.1 `config.py`

Holds **internal defaults**, not environment reads. Examples:

- default model name (e.g. `"gemini-1.5-pro"`)
- default temperature / max output tokens
- default limits (max docs per extraction, etc.)

All values can be overridden by passing explicit options from SDK/service.

#### 3.3.2 `errors.py`

Defines core exceptions:

- `DocflowError` (base)
- `SchemaError`
- `ProfileError`
- `ProviderError`
- `ExtractionError`
- `DocumentError`

These are framework‑agnostic and used across the core.

#### 3.3.3 `models/schema_defs.py`

Defines the internal schema representation used by the engine.

**Responsibilities:**

- Parse lenient JSON‑Schema‑like dicts into `InternalSchema`
- Validate model outputs against `InternalSchema` (v0.1 minimal: dict shape, required/type sanity)
- Optionally normalize outputs (fill missing fields, enforce types); unknown fields are allowed and can be preserved under an `extra` bucket.

**Key types (sketch):**

```python
@dataclass
class Field:
  name: str
  type: str  # "string", "number", etc.
  required: bool = False
  description: str | None = None

@dataclass
class RecordSet:
  name: str
  fields: list[Field]

@dataclass
class InternalSchema:
  global_fields: list[Field]
  record_sets: list[RecordSet]
```

**Key functions:**

- `parse_schema(raw: dict) -> InternalSchema`
- `validate_output(schema: InternalSchema, data: dict) -> None`
- `normalize_output(schema: InternalSchema, data: dict) -> dict`

#### 3.3.4 `models/profiles.py`

Profiles are in‑code objects that encapsulate how to extract a certain type of document.

**Key type:**

```python
@dataclass
class ExtractionProfile:
  name: str
  schema: InternalSchema | None
  mode: Literal["extract", "describe", "classify"]
  multi_mode_default: Literal["per_file", "aggregate", "both"] = "per_file"
  description: str | None = None
  provider_options: "ProviderOptions" | None = None
  prompt: str | None = None
  system_instruction: str | None = None
  params: dict | None = None
```

The SDK will map profile files (YAML/JSON) into these objects.

#### 3.3.5 `models/documents.py`

Abstracts different document sources.

**Key types:**

```python
class DocSource(Protocol):
  def load(self) -> bytes | str: ...
  def display_name(self) -> str: ...

@dataclass
class FileSource:
  path: Path

@dataclass
class GcsSource:
  uri: str  # "gs://bucket/path"

@dataclass
class RawTextSource:
  text: str
  name: str = "inline"
```

**Key function:**

- `load_content(source: DocSource) -> str | bytes`

Later this module can integrate Docling or other parsing libs. In v0.1 minimal slice, load raw bytes (no text extraction) and rely on Gemini for multimodal ingestion.

#### 3.3.6 `providers/base.py`

Defines the provider abstraction.

**Key types:**

```python
@dataclass
class ProviderOptions:
  model_name: str | None = None  # default gemini-2.5-flash
  temperature: float | None = None  # default 0.0
  max_output_tokens: int | None = None  # default None (use provider default)
  # extend as needed

class ModelProvider(Protocol):
  def generate_structured(
      self,
      prompt: str,
      schema: InternalSchema,
      options: ProviderOptions | None = None,
  ) -> dict: ...
```

The engine only knows that a provider can take a prompt + schema + options and return structured JSON.

#### 3.3.7 `providers/gemini.py`

Gemini implementation of `ModelProvider`:

- Uses `google-cloud-aiplatform` / Vertex AI
- Configures structured JSON output (schema passed as structured output; prompt stays minimal and profile-specific)
- Converts Vertex exceptions into `ProviderError`
- Defaults: model `gemini-2.5-flash`, `temperature=0.0`, `max_output_tokens=None`; usage shape `{"input_tokens": ..., "output_tokens": ...}`
- Optionally uses external libraries like **Instructor**, **Guardrails**, or **LangExtract** internally to ensure valid structured outputs (without exposing them at the public API level).

#### 3.3.8 `extraction/engine.py`

The core orchestrator.

**Signature (sketch):**

```python
def extract(
    docs: list[DocSource],
    schema: InternalSchema | None = None,
    profile: ExtractionProfile | None = None,
    provider: ModelProvider | None = None,
    options: ProviderOptions | None = None,
) -> dict:
    ...
```

**Behavior:**

1. Ensure either `schema` or `profile` is provided (schema may be `None` if the profile is intentionally schema-less).
2. Resolve `InternalSchema` (or `None`):
   - from `profile.schema` if `profile` is provided
   - from `schema` arg otherwise
3. Load document contents (possibly concatenating or annotating each doc).
4. Build prompts (system + user) from:
   - profile-specific instructions (keep prompt minimal; do **not** render schema into text)
   - multi‑doc behavior (per file vs aggregate)
5. Call `provider.generate_structured(...)` with structured-output schema (if available) and attachments.
6. If a schema is present, validate and normalize the result using `schema_defs` (minimal checks; allow extra fields); otherwise, return provider output as-is.
7. Return a dict containing structured data and optional metadata, e.g.:

   ```python
   {
     "data": {...},  # matches schema
     "meta": {
       "model": "...",
       "usage": {...},
       "docs": [...],
     },
   }
   ```

#### 3.3.9 `extraction/pipelines.py`

Placeholder for advanced flows (v0.2+):

- multi‑step extraction
- chain of providers
- table‑first extraction, etc.

For v0.1 this can be minimal or empty.

#### 3.3.10 `utils/`

- `logging.py`: common logger creator (no env reads)
- `io.py`: helpers for loading/saving schemas, reading files, etc.


## 4. SDK Layer (`docflow.sdk`)

The SDK is the **developer surface**: Python client, CLI, profile loading, and configuration.

### 4.1 Responsibilities

- Provide a `DocflowClient` that can run extractions:
  - in **local mode** (calling `docflow.core` directly)
  - in **remote mode** (calling the HTTP service)
- Implement a **profile system**:
  - built‑in profiles: `extract`, `extract_all`, `describe`
  - user‑defined profiles in YAML/JSON
  - profile resolution order: built‑in → project‑local → user‑global fileciteturn1file0
- Provide a **CLI** (`docflow`) with commands:
  - `extract`, `describe`, `run`, `profiles list`, `profiles show`
- Manage configuration:
  - CLI flags
  - environment variables
  - config file (`~/.docflow/config.toml`)
- Handle user‑facing errors and pretty output (v0.2+).
- Load profile definitions from disk (built-in packaged files + local/user overrides) including prompt, system instruction, fixed schemas, provider options, and multi-document behavior.

### 4.2 Structure

```text
docflow/sdk/
  __init__.py
  config.py
  client.py
  profiles.py
  errors.py
  cli/
    __init__.py
    main.py
```

### 4.3 Configuration (`sdk/config.py`)

Defines a simple config object and helpers to resolve configuration from:

1. CLI flags
2. Environment variables:
   - `DOCFLOW_MODE` (`local` | `remote`)
   - `DOCFLOW_ENDPOINT`
   - `DOCFLOW_PROFILE_DIR`
3. Config file `~/.docflow/config.toml`
4. Internal defaults

### 4.4 `DocflowClient` (`sdk/client.py`)

Primary Python entrypoint.

**Constructor (sketch):**

```python
class DocflowClient:
  def __init__(
      self,
      mode: Literal["local", "remote"] | None = None,
      endpoint_url: str | None = None,
      provider: ModelProvider | None = None,
      config: SdkConfig | None = None,
  ): ...
```

- If `mode` is `None`, derive from `SdkConfig`/env (`DOCFLOW_MODE`).
- `mode="local"`:
  - use core directly
  - if `provider` is `None`, create default `GeminiProvider`
- `mode="remote"`:
  - `endpoint_url` is required (or from config/env)
  - send HTTP requests to the `service`

**Main methods (aligned with previous SDK spec):**

```python
def extract(self, schema: dict, files: list[str | Path], multi_mode="per_file") -> Any: ...
def extract_all(self, files: list[str | Path], multi_mode="per_file") -> Any: ...
def describe(self, files: list[str | Path], multi_mode="per_file") -> Any: ...
def run_profile(self, profile_name: str, files: list[str | Path], multi_mode="per_file") -> Any: ...
```

Return types depend on `multi_mode`:

- `"per_file"` → `list[ExtractionResult]`
- `"aggregate"` → `ExtractionResult`
- `"both"` → `MultiResult` (with `per_file` and `aggregate`). fileciteturn1file0

Internally, the client will:

- resolve profiles via `sdk.profiles`
- convert file paths to `DocSource`s
- in local mode: call `core.extraction.engine.extract`
- in remote mode: call `POST /extract-data`

### 4.5 Profile System (`sdk/profiles.py`)

Profiles are stored as YAML/JSON on disk and converted to `ExtractionProfile` objects (per `docflow_profile_spec_v1.md`). Built-ins are also defined as files (checked in under `profiles/builtin/`) so they can carry prompt/system instructions and schemas even when they appear “schema-less” to the user.

**Locations:**

```text
./.docflow/profiles/<name>.yaml               # project-local (highest precedence)
~/.docflow/profiles/<name>.yaml               # user-global
profiles/builtin/<name>.yaml                  # bundled built-ins (lowest precedence)
```

Resolution order: project-local → user-global → built-in.

**Functions:**

- `list_profiles() -> list[str]`
- `load_profile(name: str) -> ExtractionProfile`

Profile files (v1) contain:

- `id` (required)
- `mode` (`extract` | `describe` | `classify` | future modes)
- `schema`: optional path to JSON schema (or inline object); may be `null`
- `prompt`: optional path to prompt text (or inline string)
- `system_instruction`: optional path to system instruction text (or inline string)
- `multi_doc_behavior`: optional (`per_file` | `aggregate` | `both`), defaults to `per_file`
- `params`: optional dict for future/extensible settings

Built-ins follow the same format; user/project profiles can override them by name. Profiles like `extract_all` are recipes using `mode=extract` with specific schemas/prompts (not a separate mode).

### 4.6 SDK Errors (`sdk/errors.py`)

User‑facing error types:

- `SdkError` (base)
- `RemoteServiceError` (HTTP errors)
- `ConfigError`

These may wrap core errors where appropriate.

### 4.7 CLI (`sdk/cli/main.py`)

CLI executable: **`docflow`**

#### 4.7.1 Global Options (common flags)

- `--base-url` (service endpoint for remote mode)
- `--service-account-file` (if remote auth is needed)
- `--timeout`
- `--output-format` (`print|json|excel`)
- `--output-path FILE`
- `--multi` (`per-file|aggregate|both`)
- `--verbose`

Global options follow the earlier SDK spec semantics. fileciteturn1file0

#### 4.7.2 Commands

1. **`docflow init`**  
   Writes `~/.docflow/config.toml` with defaults:

   ```bash
   docflow init      --base-url ...      --service-account-file ...      --default-output-format json      --default-output-dir ./outputs
   ```

2. **`docflow extract`**  
   Single entrypoint for extraction with two mutually exclusive modes:

   ```bash
   # Schema-based extraction (built-in "extract" profile)
   docflow extract --schema schema.json file1.pdf file2.pdf

   # Schema-less extraction (built-in "extract_all" profile)
   docflow extract --all file1.pdf file2.pdf
   ```

   - `--schema` and `--all` are mutually exclusive
   - if neither is provided, CLI prints an error and exits non‑zero
   - `--multi` overrides the profile’s default `multi_doc_behavior`

3. **`docflow describe`**  

   ```bash
   docflow describe file1.pdf file2.pdf
   ```

   Uses built‑in `"describe"` profile, with `--multi` override support.

4. **`docflow run PROFILE_NAME`**  

   ```bash
   docflow run invoice_basic file1.pdf file2.pdf
   ```

   - Resolves profile by name (built‑in → local → global)
   - Uses same output / multi options as `extract`

5. **Profile utilities**

   - `docflow profiles list` – list all profiles with a short description  
   - `docflow profiles show PROFILE_NAME` – show profile details

### 4.8 Output Formats

Initial supported formats:

- `print` – human‑friendly representation (pretty‑printed JSON or short text)
- `json` – raw JSON (to stdout or `--output-path`)
- `excel` – Excel export (v0.1 limited):

  - For a **single document**:
    - Sheet `GlobalFields`: table `field_name → value`
    - One sheet per record set: `RS_<name>`
    - Headers bold; hyperlinks when applicable
  - For **multi‑doc per_file**:
    - One Excel file per input document
  - For **multi‑doc aggregate**:
    - One consolidated workbook with the same sheet layout

(No advanced styling in v0.1.) fileciteturn1file0


## 5. Service Layer (`service/`)

The service is an optional HTTP/Pub/Sub façade built on top of `docflow.core`.  
It is **not** part of the Python package; it lives in `service/` and is used for Cloud Run deployments.

### 5.1 Responsibilities

- Expose core extraction over HTTP (`/extract-data`)
- Optionally handle Pub/Sub events for async, event‑driven pipelines
- Own environment integration:
  - GCP project IDs
  - credentials
  - Pub/Sub topics
  - logging configuration

### 5.2 Structure

```text
service/
  __init__.py              # optional
  config.py
  app.py
  handlers/
    __init__.py
    http_extract.py
    events_pubsub.py
  dependencies.py
  requirements.txt
  Dockerfile
```

### 5.3 `config.py`

- Reads env vars and builds simple config objects:

  - `DOCFLOW_DEFAULT_MODEL`
  - `DOCFLOW_GCP_PROJECT`
  - `DOCFLOW_PUBSUB_TOPIC_RESULTS`
  - etc.

### 5.4 `app.py`

- Creates the HTTP app (FastAPI/Flask/etc.)
- Registers routes:

  - `POST /extract-data`
  - `POST /events/<event_name>` (for Pub/Sub push, optional)

### 5.5 `handlers/http_extract.py`

Implements `POST /extract-data`.

**Request (JSON mode v0.1):**

```json
{
  "schema": { ... },
  "files": [
    { "uri": "gs://bucket/file.pdf", "mime": "application/pdf" }
  ],
  "profile": "optional-profile-name",
  "options": { "temperature": 0.0, "model_name": "..." }
}
```

**Behavior:**

1. Parse JSON body.
2. Build a list of `DocSource`s (e.g. `GcsSource` for `gs://` URIs).
3. Parse `schema` dict via `core.models.schema_defs.parse_schema` if present.
4. If `profile` is provided, resolve to `ExtractionProfile` (server‑side profile store or via SDK‑style resolver).
5. Build a `GeminiProvider` using `service.dependencies` and config.
6. Call `core.extraction.engine.extract(...)`.
7. Return JSON:

```json
{
  "ok": true,
  "data": { ... },   // structured output
  "meta": {
    "model": "...",
    "usage": { ... }
  }
}
```

On error, respond with:

```json
{
  "ok": false,
  "error": {
    "type": "SchemaError",
    "message": "..."
  }
}
```

with appropriate HTTP status codes.

### 5.6 `handlers/events_pubsub.py` (Optional)

Implements endpoints for Pub/Sub push (e.g. `POST /events/extractions.request`).

- Decode Pub/Sub envelope
- Validate event payload
- Call `core.extraction.engine.extract(...)`
- Store result (e.g. in GCS under `results/{request_id}.json`)
- Publish follow‑up event (`extractions.ready`) with result URI

### 5.7 `dependencies.py`

- Factory functions to create:
  - `ModelProvider` (e.g. `GeminiProvider`) from config/env
  - clients for GCS, Pub/Sub
  - loggers

Service remains a thin shell that wires env/config to the core.

### 5.8 Auth and Error Mapping (v0.1)

- Auth: Cloud Run IAM (`roles/run.invoker`) only; no bearer tokens/API keys/custom headers required beyond existing Google credentials. Local dev can be open.
- Error → HTTP status mapping:
  - `SchemaError`: 400
  - `DocumentError`: 400
  - `ProfileError`: 404
  - `ProviderError`: 502
  - `ExtractionError`: 500
  - Other: 500
- Error response shape: `{"ok": false, "error": {"type": "...", "message": "..."}}`



## 6. External Libraries and Providers

DocFlow is **provider‑agnostic** at the core level. New providers can be added under `core/providers/`:

- `gemini.py` (initial)
- `openai.py`
- `anthropic.py`
- `mock.py` for testing

Each provider implements `ModelProvider` and can internally use structured‑output libraries such as:

- **Instructor** – Pydantic‑based structured outputs
- **Guardrails** – schema enforcement and re‑tries
- **LangExtract** – higher‑level extraction with LLMs

These libraries are optional and must be encapsulated inside provider implementations; the engine interacts only with `ModelProvider`.



## 7. Implementation Roadmap (High‑Level)

This section is qualitative on purpose: it describes **phases** rather than timelines.

### Phase 1 – Minimal Vertical Slice

Goal: run a simple extraction end‑to‑end in **local mode**.

1. Implement `InternalSchema` + `parse_schema` with a minimal subset (just global fields).
2. Implement `DocSource` (at least `FileSource`) and `load_content`.
3. Implement `ProviderOptions`, `ModelProvider`, and `GeminiProvider.generate_structured(...)` with a basic call to Gemini JSON output.
4. Implement `engine.extract(...)` for a simple case:
   - single file
   - schema with a few fields
   - return raw JSON from provider
5. Implement `DocflowClient(mode="local")` that wraps `engine.extract`.
6. Implement a minimal `docflow extract --schema ... file.pdf` CLI command.

Once this works, you already have a usable local library for experiments and agents.

### Phase 2 – Profiles, Multi‑doc, and CLI Features

1. Implement `ExtractionProfile` and SDK profile loader (YAML/JSON).
2. Add built‑in profiles: `extract`, `extract_all`, `describe`.
3. Implement multi‑document modes:
   - `per_file`
   - `aggregate`
   - `both`
4. Implement result wrappers (`ExtractionResult`, `MultiResult`) and mapping from engine output.
5. Extend the CLI:
   - `docflow extract --all`
   - `docflow describe`
   - `docflow run PROFILE_NAME`
   - `docflow profiles list/show`
6. Add output formats (`print`, `json`, `excel` for simple cases).

### Phase 3 – Remote Mode and Service

1. Implement remote mode in `DocflowClient`:
   - HTTP POST to `/extract-data`
2. Implement the `service/` app with `POST /extract-data` handler using core.
3. Build and deploy service to Cloud Run.
4. Extend SDK config (`DOCFLOW_MODE`, `DOCFLOW_ENDPOINT`) and `docflow init` command.

### Phase 4 – Refinement and Integrations

1. Hardening:
   - better error mapping and messages
   - timeouts and retries
2. Advanced provider logic:
   - integrate Instructor/Guardrails/LangExtract inside `GeminiProvider` if needed
3. Document parsing integration (Docling or similar) for robust PDF handling.
4. Multi‑step pipelines in `pipelines.py` if required by real use cases.


## 8. Conceptual View of the Project

DocFlow gives you:

- a **clean core** that any agent or service can import
- a **nice SDK + CLI** for your day‑to‑day work and demos
- an optional **service façade** for pipelines and multi‑language consumers

It avoids “scripts everywhere” by centralizing:

- how schemas are interpreted
- how prompts are built
- how providers are called
- how outputs are validated and delivered

At the same time, it stays pragmatic:

- Gemini is the first provider, but the design keeps the door open for others
- the SDK and CLI are opinionated but can be extended over time
- external libraries (Instructor, Guardrails, LangExtract) can be plugged in where they actually add value, not as hard dependencies.
