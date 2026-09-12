# DuckDB community extension

Last updated: 2026-09-12.

**duckdb-apple-health** ships the DuckDB C scanner as community extension
**`healthkit_export`** (macOS first):

```sql
INSTALL healthkit_export FROM community;
LOAD healthkit_export;
```

- First listing (name **`apple_health`**, superseded): https://github.com/duckdb/community-extensions/pull/2653
- Current package name: **`healthkit_export`** (v**0.2.0**, C API stamp **v1.2.0**)
- Descriptor path: `extensions/healthkit_export/description.yml`
- Platforms: **`osx_arm64`**, **`osx_amd64`** for DuckDB **v1.5.5**
- Linux / Windows / Wasm: still excluded until multi-platform CI is widened

Related: [DESIGN.md](DESIGN.md) · [RELEASE_PLAN.md](RELEASE_PLAN.md) · [VERSIONING.md](VERSIONING.md) · [ROADMAP.md](ROADMAP.md).

---

## Status

| | |
|--|--|
| First community PR | [#2653](https://github.com/duckdb/community-extensions/pull/2653) published `apple_health` (superseded by rename) |
| Current name | **`healthkit_export`** (v0.2.0) |
| CDN (example) | `https://community-extensions.duckdb.org/v1.5.5/osx_arm64/healthkit_export.duckdb_extension.gz` |
| Verified | `INSTALL` / `LOAD` + fixture queries on DuckDB **1.5.5** (macOS arm64) |

## What “community extension” means

DuckDB’s [community extensions](https://duckdb.org/community_extensions/) are **not**
uploads of your `.duckdb_extension` binaries.

1. You open a PR on [duckdb/community-extensions](https://github.com/duckdb/community-extensions)
   with a single descriptor: `extensions/apple_health/description.yml`.
2. Their CI clones **this** GitHub repo at a **pinned commit SHA** (`repo.ref`).
3. They build with the shared extension toolchain for supported platforms.
4. DuckDB **signs** the binaries and hosts them.
5. Users on a **recent stable** DuckDB get `INSTALL … FROM community`.

You keep developing in **Mjboothaus/duckdb-apple-health**. Community is a **distribution
channel**, not a second source tree (unless you later split monorepo concerns).

---

## What stays in this repo vs what community ships

| In this monorepo | Community `INSTALL healthkit_export` |
|------------------|----------------------------------|
| C extension (`src/`, `duckdb_capi/`, template Makefile) | **Yes** — this is what they build |
| SQLLogic under `test/sql/` | **Yes** — should pass in their CI |
| Fixture `test/data/` (synthetic only) | **Yes** — needed for tests |
| Python `health-data-store`, marimo, maps, Photos | **No** — never inside the extension binary |
| Personal `output/`, real exports | **No** — never in git or CI |

Python add-ons remain optional ([PYTHON_PACKAGE.md](PYTHON_PACKAGE.md)). Do **not** try to
ship maps/Photos via community install.

---

## Prerequisites before opening the community PR

### Product / correctness (Layer A freeze)

- [ ] Tagged release (e.g. **v0.1.0**) whose tree is the intended `repo.ref` (or a later patch tag).
- [ ] Clean clone: `just bootstrap` (or `just configure && just debug && just fixture`).
- [ ] `just test` / SQLLogic green (`test/sql/*.test`).
- [ ] `just pytest-ext` green (fixture golden + optional healthkit-to-sqlite compare).
- [ ] README table-function contract matches the binary (names, columns, path kinds).
- [ ] Honest limits documented (bind buffer, no community install until this lands, unsigned interim).

### Technical / toolchain

This project uses **`duckdb/extension-template-c`** (stable **C API**), not the classic C++
`extension-template`.

- [ ] Confirm community CI can build **C-API / C_STRUCT** extensions (template README historically said community support was maturing — verify current status on Discord / recent community PRs).
- [ ] Multi-arch builds green under **this** repo’s GitHub Actions (`MainDistributionPipeline.yml` / extension-ci-tools), or a documented subset (`osx_arm64` first is fine for a personal v0.1 tag; community usually wants the full matrix).
- [ ] Extension **name** unique: propose `healthkit_export` (matches binary / `LOAD` name). Must match `^[a-z][a-z0-9_-]*$`.
- [ ] No network I/O or secrets in the extension (already a design rule).
- [ ] Licence Apache-2.0 (already).

### Process

- [ ] Choose maintainers list (GitHub handles) for the descriptor.
- [ ] Pin `repo.ref` to an **immutable commit** on `main` (tag annotated preferred).
- [ ] Prepare a short `docs.hello_world` SQL snippet for the auto-generated docs page.

If C-API community CI is not ready, fall back to:

1. GitHub Release **unsigned** binaries per platform, or  
2. Self-hosted extension repository layout (see below),

and keep this doc for when the official path opens.

---

## Descriptor sketch (`description.yml`)

File location in the **community-extensions** fork:

`extensions/apple_health/description.yml`

```yaml
extension:
  name: healthkit_export
  description: >
    Read Apple Health export.zip / export.xml as typed DuckDB tables
    (records, workouts, activity summaries, workout routes and GPX points).
  version: 0.1.0
  language: C
  build: cmake
  license: Apache-2.0
  maintainers:
    - Mjboothaus
  # excluded_platforms: wasm_mvp;wasm_eh;wasm_threads   # if needed
  # requires_toolchains: ...                            # only if CI needs extras

repo:
  github: Mjboothaus/duckdb-apple-health
  ref: REPLACE_WITH_COMMIT_SHA_OF_v0.1.0   # not a floating branch name

docs:
  hello_world: |
    -- After: INSTALL healthkit_export FROM community; LOAD healthkit_export;
    SELECT type_short, count(*) AS n
    FROM read_healthkit_export('export.zip')
    GROUP BY 1
    ORDER BY n DESC
    LIMIT 10;
  extended_description: |
    HealthKit-shaped scanner on DuckDB's stable C API. Large exports should be
    scanned once and materialised to Parquet or a local DuckDB file (see project README).
    Does not include Python maps/Photos helpers — those live in the same GitHub
    repo as an optional companion package.
```

Open a PR with **only** that file (plus any community-repo conventions). Their CI builds
and reports failures on your `ref`.

### Updating a published extension

1. Land fixes on this repo; tag if needed.  
2. PR to community-extensions: bump `extension.version` and `repo.ref` (and `repo.ref_next` around DuckDB releases if required).  
3. Merge rebuilds and republishes.

---

## Keep this monorepo or split?

**Recommendation for v0.1–v0.2: keep one repo.**

| Approach | Pros | Cons |
|----------|------|------|
| **Monorepo** (current) | One clone for persona; shared VERSION; community builds from same history | CI must not require Python extras for extension jobs |
| **Extension-only repo** | Cleaner community surface | Dual maintenance; copy fixtures/docs; version drift |

Community only needs the C tree + tests + fixture. You can later:

- Extract `extension/` into `duckdb-apple-health-ext`, or  
- Teach community CI to build from a subdirectory (if supported),

but that is optional. Until then, ensure extension CI paths ignore heavy Python extras.

---

## Local / interim distribution (developers)

### A. Unsigned local build

```bash
just bootstrap
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/healthkit_export/healthkit_export.duckdb_extension';
FROM read_healthkit_export('test/data/export.zip');
```

### B. GitHub Release binaries

Attach per-platform `.duckdb_extension` files to the **v0.1.0** GitHub Release. Users still
need unsigned load / trust your build. Document platform + DuckDB version matrix.

### C. Self-hosted repository

Layout DuckDB already understands:

```text
https://example.com/extensions/
  v1.5.x/          # or version directory DuckDB expects for your build
    osx_arm64/
      healthkit_export.duckdb_extension
    linux_amd64/
      ...
```

```sql
INSTALL healthkit_export FROM 'https://example.com/extensions';
```

Binaries are typically **unsigned** unless you operate a signing story. Useful if community
C-API CI lags.

---

## Suggested sequence (extension-only completion → community)

```text
1. Merge add-ons PR if still open; cut Layer A focus branch if needed
2. Phase 1 freeze checklist (tests, README TF matrix, limits)
3. Tag v0.1.0 · rebuild · verify extension metadata = tag
4. Optional: GH Release unsigned binaries (osx_arm64 first)
5. Confirm C-API community CI readiness
6. PR description.yml → duckdb/community-extensions
7. After merge: README switches default install story to INSTALL FROM community
```

Python / walk-stories stay on the “optional add-ons” path and must not gate steps 2–6.

---

## Name collisions and branding

- Extension name **`healthkit_export`** is descriptive of the **export format**, not an Apple product claim. Keep README clear: third-party scanner for Health **exports**.
- If community maintainers require a rename, prefer `apple_health_export` or `healthkit_export` and plan a SQL alias period — cheaper before first community publish than after.

---

## Checklist copy-paste

**v0.1.0 core (this repo)**

- [ ] bootstrap / debug / fixture  
- [ ] SQLLogic + pytest-ext  
- [ ] README TF matrix + QUICKSTART Rungs 1–2  
- [ ] CHANGELOG / RELEASE_NOTES (core vs add-ons)  
- [ ] Tag `v0.1.0` + extension metadata  
- [ ] Optional multi-arch CI artifact  

**Community**

- [ ] C-API build confirmed in community toolchain  
- [ ] `description.yml` PR  
- [ ] Docs page smoke (`hello_world`)  
- [ ] README install section updated  

**Explicit non-goals for community binary**

- [ ] No Python wheel inside extension  
- [ ] No real Health export in CI  
- [ ] No Wasm unless separately staffed  

---

## References

- Community development: https://duckdb.org/community_extensions/development.html  
- Community docs / submit: https://duckdb.org/community_extensions/documentation.html  
- C API template: https://github.com/duckdb/extension-template-c  
- Community repo: https://github.com/duckdb/community-extensions  
- This project: https://github.com/Mjboothaus/duckdb-apple-health  
