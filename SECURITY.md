# Security and privacy

## What this extension does

`duckdb-apple-health` reads a **local filesystem path** you supply (Health `export.zip` / `export.xml` / directory) and exposes rows to DuckDB SQL inside the same process.

- **No network I/O** in the extension
- **No telemetry**
- **No cloud upload**

## Handling Health data

Apple Health exports can contain highly sensitive personal information.

- Do **not** commit real `export.zip` / `export.xml` files to git
- Do **not** paste PHI into GitHub issues, PRs, or CI logs
- Prefer synthetic fixtures (`just fixture`) for development
- When filing bugs against real exports, describe shape/counts/errors — not raw samples

## Reporting vulnerabilities

If you believe you have found a security issue in this repository (for example path handling that reads unexpected files, memory safety in the C parser, or accidental data exfiltration via a dependency):

1. Email **michael@databooth.com.au** with a description and reproduction steps if possible.
2. Avoid opening a public issue with exploit details until a fix is available.
3. We will aim to acknowledge within a few business days (best effort for a small maintainer set).

## Supply chain notes

- Runtime core is C + zlib + DuckDB’s C API headers vendored as `duckdb_capi/`
- Python (`uv`, pytest, marimo, healthkit-to-sqlite) is for **dev/test/docs** only, not required to load the `.duckdb_extension` in DuckDB CLI
- Load only binaries you built yourself or trust; v0.1 uses **unsigned** `LOAD`

## Supported versions

Only the latest **v0.1.x-beta** line on `main` is actively maintained until a stable release exists.
