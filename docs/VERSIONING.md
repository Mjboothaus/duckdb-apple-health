# Versioning

Last updated: 2026-09-06.

This repo ships **two related artefacts** with coordinated SemVer:

| Artefact | Where the version lives | What consumers see |
|----------|-------------------------|-------------------|
| **C extension** (`healthkit_export.duckdb_extension`) | Git **tag** at build time → `configure/extension_version.txt` → extension metadata | DuckDB `LOAD` metadata / `extension_version` field |
| **Python supplementary package** (optional Layer B/C: `python/health_data_store`, notebooks) | `pyproject.toml` `[project].version` and root **`VERSION`** file | `uv` / future pip metadata; docs. **Not** required to use the extension. v0.1 does **not** require PyPI. |

## Source of truth

- Root file **`VERSION`** — bare SemVer, e.g. `0.1.0` (no leading `v`).
- Release tags are **`v` + VERSION**, e.g. `v0.1.0`.
- Pre-releases use SemVer prerelease: `0.1.0-beta` → tag `v0.1.0-beta`.

Keep these in sync on every release:

1. `VERSION`
2. `pyproject.toml` → `version = "…"`
3. `docs/RELEASE_NOTES.md` / `CHANGELOG.md`
4. Git tag `v…`
5. Rebuild extension so metadata picks up the tag (`just configure && just debug` or `just release`)

Helper: `just version` prints current values; `just version-sync` writes `VERSION` into `pyproject.toml`.

## Supplementary Python package

- **Purpose:** local DB, maps, Photos, journeys, tests — not the scan engine.
- **Today:** root project uses uv with `package = true` (develop against the repo).
- **v0.1.0:** ship docs + working `uv sync` / `just` recipes; no publish requirement.
- **Later:** installable package + optional extras; keep SemVer aligned with root `VERSION` until a deliberate split.
- Full product framing: [RELEASE_PLAN.md](RELEASE_PLAN.md) § Python packaging decision; [ROADMAP.md](ROADMAP.md).


## Extension version (how the template works)

`extension-ci-tools` `configure` / `extension_version` target:

1. If `git tag --points-at HEAD` is set → that string is the extension version.
2. Else → short git commit hash (e.g. `1e56d92`).

So **untagged builds embed a git hash**, not SemVer. For a release build you must:

```bash
# on main, VERSION already bumped
git tag -a "v$(cat VERSION)" -m "Release v$(cat VERSION)"
just configure   # refreshes configure/extension_version.txt
just release     # or just debug
# confirm metadata shows v0.1.0 (not a bare hash)
```

Do **not** hand-edit `configure/extension_version.txt` for releases — it is generated (and `configure/` is gitignored).

## Python package version

`pyproject.toml` currently has `package = true` (app/tooling, not published to PyPI yet). Version still matters for:

- Reproducible `uv lock` / environment identity
- Future optional publish of `health_data_store` helpers
- Aligning docs with “add-ons v0.1.0”

Until publish:

```toml
[project]
name = "health-data-store"
version = "0.1.0"   # must match VERSION
```

When publishing later, prefer a clear name (e.g. `health-data-store`) and the same SemVer as the extension **major.minor** where practical; patch may diverge if only Python changes.

## Layer alignment (see RELEASE_PLAN.md)

| Release | Extension tag | Python `VERSION` | Notes |
|---------|---------------|------------------|-------|
| Core only | `v0.1.0` | `0.1.0` | Add-ons may still be “preview” in docs |
| Add-ons studio | `v0.1.0` (unchanged) or `v0.1.1` if ext bugfix | `0.1.1` or `0.2.0` | Prefer bumping Python when only B/C change |
| Breaking ext API | `v0.2.0` | `0.2.0` | Document TF changes |

## Checklist every release

- [ ] Bump `VERSION`
- [ ] `just version-sync` (or manual pyproject edit)
- [ ] Update CHANGELOG + RELEASE_NOTES
- [ ] Commit on `main`
- [ ] `git tag -a v$(cat VERSION) -m "…"`
- [ ] `just configure && just release` (or debug)
- [ ] Verify extension metadata version string
- [ ] `git push origin main --tags`
- [ ] GitHub Release from the tag

## Related

- [RELEASE_PLAN.md](RELEASE_PLAN.md)
- [PERSONA.md](PERSONA.md)
- [CHANGELOG.md](../CHANGELOG.md)
