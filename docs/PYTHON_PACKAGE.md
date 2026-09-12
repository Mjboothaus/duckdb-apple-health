# Python package — `health-data-store`

Last updated: 2026-09-06.

Companion library for the **duckdb-apple-health** C extension. It owns the **local DuckDB health store** and optional walk/map/Photos helpers. It is **not** required to `LOAD` the extension or run SQL table functions.

## Why this name (not “explore”, not “Apple”)

| Candidate | Verdict |
|-----------|---------|
| `health-data-store` | **Chosen.** Matches the durable artefact (`HealthDataStore`, `just build-db`, local `.duckdb` file). Neutral; no Apple trademark in the package name. |
| `health-data-explore` | Good product *verb*, weaker library name. Exploration UIs (marimo) are still **experimental** and optional; naming the whole package after them oversells Layer C. |
| `apple-health-*` | Avoid on PyPI; keep “Apple Health export” in prose only. |

Import: `health_data_store`. Class name stays `HealthDataStore`.

## Repo strategy: extension + add-ons together

**Keep one public repo** (`duckdb-apple-health`) for now:

| In this repo | Role |
|--------------|------|
| C extension (`healthkit_export`) | Layer A — scanner; future community `INSTALL` candidate |
| `health-data-store` Python | Layers B/C — local DB, maps helpers, scripts, experimental notebooks |

**Do not** split to a second GitHub repo until the extension is on community (or clearly blocked) *and* the Python package has independent users. One clone, one VERSION line of sight, simpler for the persona.

When community publish lands, the **extension binary** is built from this same repo at a pinned commit; the Python wheel is a separate optional artefact (editable here; PyPI later).

## Community extension path (Layer A)

Target UX:

```sql
INSTALL healthkit_export FROM community;
LOAD healthkit_export;
```

That is the supported “publish” path: PR a single `extensions/apple_health/description.yml` to [duckdb/community-extensions](https://github.com/duckdb/community-extensions); DuckDB CI builds, signs, hosts.

**Gates before we open that PR**

1. v0.1.0 tagged; fixture + SQLLogic/pytest green on the pinned commit  
2. Multi-platform CI matching community toolchain (template C-API support — confirm with Discord/docs; C template still maturing vs C++)  
3. Stable table-function surface documented  
4. Honest docs: scan vs Parquet; unsigned interim  

**Until then:** unsigned local `LOAD` + optional GitHub Release binaries. Self-hosted extension repo is a fallback if community C-API CI is not ready.

The **Python package is never** what community `INSTALL` distributes. Maps/Photos/marimo stay out of the extension binary.

## Install (from this repo)

```bash
just uv-sync
# or:
uv sync --all-extras --group dev
```

Extras:

```bash
uv sync --extra maps
uv sync --extra notebooks   # experimental marimo apps
uv sync --extra dev
uv sync --all-extras
```

Future PyPI (not a v0.1 gate):

```bash
pip install 'health-data-store[maps]'
```

## Extras

| Extra | Adds | Enables |
|-------|------|---------|
| *(base)* | duckdb, pandas, pyyaml, pytz | `HealthDataStore`, journeys, places, Photos via DuckDB `ATTACH` (no osxphotos) |
| `maps` | folium | `build_route_map`, scripted/HTML maps — **preferred** map path for v0.1 |
| `notebooks` | marimo, altair, polars, folium | `explore_export` / `map_walks` / `walk_stories` — **experimental** |
| `dev` | pytest, healthkit-to-sqlite | extension golden tests |
| `all` | union | full local studio |

### Marimo status

Marimo notebooks under `notebooks/` are **not fully verified**. Prefer:

- SQL + extension demos (`just demo`)  
- `just build-db` + DuckDB CLI  
- Folium via `health_data_store.maps` / scripts  

Treat `just map-walks` / `just walk-stories` as preview until smoke-tested on a real local DB.

## Imports

```python
from health_data_store import HealthDataStore, find_extension
# maps extra:
from health_data_store import build_route_map, downsample_points
```

Optional symbols are **lazy** — base import does not require Folium.

## Versioning

Root `VERSION` + `just version-sync`. See [VERSIONING.md](VERSIONING.md).

## Related

- [RELEASE_PLAN.md](RELEASE_PLAN.md)
- [PERSONA.md](PERSONA.md)
- [ROADMAP.md](ROADMAP.md)
- [ERD.md](ERD.md)
