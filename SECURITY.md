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

1. Open a [GitHub issue](https://github.com/mjboothaus/duckdb-apple-health/issues/new) with a clear description and reproduction steps if possible.
2. Do **not** include real Health export data, PHI, or exploit payloads in the issue body or attachments.
3. For sensitive details you prefer not to post publicly, say so in the issue and keep the public description high-level until maintainers respond.
4. Acknowledgement is best effort for a small maintainer set.

## Supply chain notes

- Runtime core is C + zlib + DuckDB’s C API headers vendored as `duckdb_capi/`
- Python (`uv`, pytest, marimo, healthkit-to-sqlite) is for **dev/test/docs** only, not required to load the `.duckdb_extension` in DuckDB CLI
- Load only binaries you built yourself or trust; v0.1 uses **unsigned** `LOAD`

## Supported versions

Only the latest **v0.1.x-beta** line on `main` is actively maintained until a stable release exists.
