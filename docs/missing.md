# Remaining Gaps (tracking)

- CLI profile workflows: `docflow profile create/edit` not yet implemented.
- Service alignment: FastAPI handler should load profiles from files, pass attachments, and emit the standardized `ok/error` envelope with usage/meta.
- Provider attachments: MIME guessing added (mimetypes + fallback), but could be improved with richer DocSource metadata (content-type hints).
- Auth/output mapping in service: adopt clarified HTTP error mapping and response shape.
