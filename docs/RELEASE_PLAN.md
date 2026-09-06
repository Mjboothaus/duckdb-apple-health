# Initial release plan — extension core, local DB, add-ons

Last updated: 2026-09-05.

Persona and onboarding ladder: [PERSONA.md](PERSONA.md).

## Purpose

Get to a **reviewable first release** with three clear layers:

1. **Layer A — Core** — DuckDB C extension (scanner): correct, testable, documentable  
2. **Layer B — Local enriched DB** — `output/apple_health.duckdb` + Python store (build once, query often)  
3. **Layer C — Add-ons** — maps, places, photos, multi-section journeys, marimo apps (optional product surface)

**Release rule:** A must ship **without** B/C. B must work with CLI/SQL only. C is “batteries included” for the persona’s storytelling path.

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│  LAYER A — Core extension (C, Apache-2.0, privacy-hard)     │
│  read_apple_health / workouts / summaries / routes / points │
│  fixtures · SQLLogic · pytest · unsigned LOAD               │
└───────────────────────────┬─────────────────────────────────┘
                            │ just build-db (scan once)
┌───────────────────────────▼─────────────────────────────────┐
│  LAYER B — Local enriched database (Python + DuckDB file)   │
│  gps.* · route_points_map · ingest_manifest                 │
│  route_places · walk_photos · journeys / journey_sections   │
│  HealthDataStore · scripts/* · just recipes                 │
└───────────────────────────┬─────────────────────────────────┘
                            │ optional UI
┌───────────────────────────▼─────────────────────────────────┐
│  LAYER C — Add-ons (marimo / HTML export)                   │
│  explore_export · map_walks · walk_stories                  │
│  Folium · filmstrip · full-size photo popup · journeys UI   │
└─────────────────────────────────────────────────────────────┘
```

## Current state (snapshot)

Last refreshed: 2026-09-06. Repo: **https://github.com/Mjboothaus/duckdb-apple-health** (no DataBooth branding in tree).

### On `main` (merged)

- Extension TFs: records, workouts (+ stats/events), activity summaries, clinical, routes, route points; zip DEFLATE  
- Local DB bootstrap (`just build-db`), ERD, docs (`PERSONA`, `RELEASE_PLAN`, `VERSIONING`, …)  
- Photos / journeys / maps / walk-stories path (PRs **#21**, **#22**); DuckDB 2.0-alpha experiment (**#20**, non-blocking); rebrand + versioning (**#24**)  
- `HealthDataStore`, map helpers, `route_places`, free tiles  

### Open PRs

None required for docs/positioning. Feature work continues via normal branches.

### Local / optional polish still open

- Walk-stories UX polish if any remaining stash or notebook tweaks  
- Personal journey YAML/HTML under gitignored `output/` (not shipped)  
- GNW: Olney catch-up; Bar Beach → Queens Wharf photo-implied gap (Layer C quality)  

### Known product gaps (not core blockers for v0.1.0)

- Extension still bind-buffers full scans — **document honestly** (README performance section); optimise after v0.1  
- Dual DuckDB 1.x / 2.0-alpha build incomplete  
- Python still `package = true` (app-style uv project); treat as **supplementary package** (see below)  

## Versioning

Details and release checklist: [VERSIONING.md](VERSIONING.md) (root `VERSION`, extension git tag metadata, `pyproject.toml`).

| Tag | Meaning |
|-----|---------|
| **v0.1.0** | **Core extension** release (Layer A solid); B minimally documented; C optional/experimental |
| **v0.2.0** (or later) | B+C “studio” add-ons maturity; optional first **PyPI** of the supplementary Python package |

Prefer **core first**, then add-ons maturity, so extension-only users are not blocked on Photos/marimo.

## Distribution strategy (extension vs Python)

**One repo** for v0.1: C extension + `health-data-store` add-ons ([PYTHON_PACKAGE.md](PYTHON_PACKAGE.md)).

| Artefact | Publish path | v0.1 |
|----------|--------------|------|
| Extension | Community `INSTALL apple_health FROM community` when C-API CI allows; until then unsigned `LOAD` / optional GH Release binaries | Core freeze + tag; community PR **after** gates |
| Python | Editable `uv sync`; optional later PyPI `health-data-store[maps,…]` | Package structure yes; PyPI **not** required |
| Marimo maps/stories | In-repo notebooks only | **Experimental** — not a release blocker |

Do **not** split the Python package to another GitHub repo until the extension is published (or blocked) and add-ons have standalone demand.

Community install migration (descriptor, gates, monorepo vs split): [CREATE_COMM_EXT.md](CREATE_COMM_EXT.md).

## Python packaging decision (supplementary package)

**Question:** are we wrapping the Python bits as a supplementary package?

**Answer: yes — as a product decision — without making PyPI a v0.1 gate.**

| | |
|--|--|
| **Role** | Layer B/C only: fixtures, pytest, `HealthDataStore`, `build-db`, maps, Photos, journeys, marimo |
| **Not** | Required to `LOAD` the extension or run SQL table functions |
| **Layout today** | `python/health_data_store/` + root `pyproject.toml` with **`package = true`** (uv application / monorepo style) |
| **Version** | Same root **`VERSION`** / `just version-sync` as the extension line of sight ([VERSIONING.md](VERSIONING.md)) |
| **v0.1.0** | Document the tree; keep `uv sync` working; **do not** require publish |
| **Later** | Flip to an installable package (`health-data-store` or aligned with repo), optional extras (`maps`, `photos`, `notebooks`), then consider PyPI |

Do **not** put Python inside the C extension binary. Do **not** block the core release on packaging polish.

---

## Phase 0 — Land and organise WIP (1–2 days)

**Goal:** clean git story.

1. ~~**PR order:** merge **#21** then **#22**; triage **#20**.~~ **Done** (plus rebrand **#24**).  
2. **Follow-up:** any remaining `walk_stories` / map polish still local → small PR; **do not** commit personal `output/journeys/*.yml`.  
3. **Docs:** PERSONA, this plan, VERSIONING, ROADMAP, README positioning/performance — keep linked from [docs/README.md](README.md).  
4. **Label commits** by layer where practical (`ext:`, `db:`, `addon:`, `docs:`).

**Exit:** `main` builds; architecture and persona documented; ready for Phase 1 core freeze.

---

## Phase 1 — Core extension release-ready (Layer A)

**Goal:** v0.1.0 you would hand a DuckDB power user (persona Rungs 1–2).

### 1.1 Correctness freeze

- [ ] `just bootstrap` / `just debug` on clean clone  
- [ ] `just pytest-ext` + SQLLogic green  
- [ ] README TF matrix complete and accurate  
- [ ] Fixture golden + Correlation/top-level semantics documented  
- [ ] Optional real-export smoke documented (not required in CI)  

### 1.2 Packaging (unsigned is acceptable for this persona)

- [ ] Tag **v0.1.0**  
- [ ] osx_arm64 build instructions; optional CI artifact  
- [ ] QUICKSTART = Rungs 1–2 only  
- [ ] CHANGELOG + RELEASE_NOTES: core vs Python add-ons  
- [ ] Compatibility: DuckDB 1.5.x unsigned; 2.0 strategy noted  

### 1.3 Honest limits (ship in notes)

- Bind-time full buffer (RAM ∝ export)  
- Full zip member inflate to temp  
- No named `types` / `start` / `end` yet  
- No community `INSTALL` yet  

### 1.4 DuckDB version strategy

| Option | Recommendation |
|--------|----------------|
| Pin stable metadata + 1.5.x CLI (current main) | **v0.1.0 default** |
| Dual `debug` / `debug-alpha` | After core tag, or docs-only experiment (#20) |
| Wait for 2.0 GA | Strategic, not initial-release blocker |

### 1.5 Out of v0.1.0 core

Streaming execute/zip, workout events/statistics TFs, ECG/clinical, Wasm, community INSTALL.

**Exit:** tagged core; README “Core extension” stands alone.

---

## Phase 2 — Local enriched database (Layer B)

**Goal:** persona Rungs 3–4 without marimo.

### 2.1 Schema (see [ERD.md](ERD.md))

| Table / view | Role | Status |
|--------------|------|--------|
| `workouts` / `routes` / `route_points` / `route_points_map` | GPS core | On main |
| `ingest_manifest` | Provenance | On main |
| `route_places` | Start/end labels | On main (#19) |
| `walk_photos` | Photo match | #21 + local |
| `journeys` / `journey_sections` | Multi-day trails | #22 + local |

### 2.2 Documented CLI surface

```bash
just build-db export_zip=…
just list-walks 20
just geocode-places -- --limit 100
just photos-for-walks -- --limit-walks 50
just journey-import path/to.yml
just journey-list
```

### 2.3 Hardening

- [ ] `HealthDataStore` API listed in docs  
- [ ] Fix/document DuckDB attach lock (photos ATTACH vs open store)  
- [ ] Cocoa date offset for Photos.sqlite documented  
- [ ] Privacy: `output/` gitignored; example YAML only in `docs/`  
- [ ] Tests skip cleanly without personal DB  
- [ ] Incremental append-by-`gpx_path` — **post** initial DB toolkit (roadmap Option B)  

**Exit:** docs-only path builds DB and queries walks/places/photos/journeys via just/SQL.

---

## Phase 3 — Add-ons (Layer C)

**Goal:** persona Rung 5; clearly marked optional/preview.

### 3.1 Ship set

| Add-on | Entry | Depends on |
|--------|-------|------------|
| Explore metrics | `notebooks/explore_export.py` | A |
| Single-walk map | `just map-walks` | B |
| **Journey stories** | `just walk-stories` | B journeys + photos |
| HTML snapshot | `output/maps/*_elegant.html` | Same helpers; shareable |

### 3.2 walk-stories acceptance (major walks)

For **Camino del Norte**, **Abel Tasman**, **Three Capes**, **Six Foot** (GNW when ready):

- [ ] Journey picker  
- [ ] Section list + focus one section  
- [ ] Map: section colours + start/end name chips  
- [ ] Photos: pins + filmstrip; click → full-size popup  
- [ ] Calm empty state if no photos  

### 3.3 Journey data quality (product, not core)

- [x] Six Foot = 2 GPS days (local)  
- [ ] Abel/Three Capes: drop noise fragments if needed  
- [ ] GNW: Olney catch-up; Bar Beach → Queens Wharf photo-implied leg  
- [ ] Personal manifests stay in `output/journeys/`  

### 3.4 Packaging

- [ ] README **Add-ons (optional)** + Photos privacy warning  
- [ ] Optional dependency groups if lockfile bloat hurts  
- [ ] Tag **v0.1.0-addons** or “studio preview” alongside core  

---

## Phase 4 — Explicit backlog (do not block initial release)

| Item | Layer |
|------|-------|
| Streaming execute + zip inflate | A |
| Named TF parameters | A |
| DuckDB 2.0 GA / community INSTALL | A |
| DB append-by-`gpx_path` | B |
| Journey suggest (end→start proximity) | C |
| Workout events/statistics TFs | A |
| ECG / clinical | later |

---

## Suggested calendar

| Week | Focus |
|------|--------|
| **W0** | Phase 0: merge #21/#22; walk_stories PR; link PERSONA + this plan from docs index |
| **W1** | Phase 1: core freeze, docs, tag **v0.1.0** |
| **W2** | Phase 2: DB toolkit docs + photo/connection hardening |
| **W3** | Phase 3: walk-stories QA on major journeys; optional addons tag |
| **W4+** | GNW gaps; streaming execute if needed |

---

## Decisions (defaults)

1. **Monorepo** with clear A/B/C labels — yes.  
2. **Photos not required for core v0.1.0** — yes.  
3. **Streaming execute does not block v0.1.0** — yes; document limits.  
4. **#20 (2.0-alpha) not required for v0.1.0** — yes unless dual-target finished.  
5. **Never commit personal journey path lists** — yes.

---

## Immediate next actions (after review)

1. Approve/adjust this plan + [PERSONA.md](PERSONA.md).  
2. Merge #21 → #22; PR remaining walk_stories polish.  
3. Core release checklist → tag v0.1.0.  
4. Then DB/add-on polish and GNW completeness.

## Success criteria

- **Core:** technical Apple user clones, builds, `LOAD`s, runs fixture + own zip demos, understands limits.  
- **DB:** same user builds personal DB and queries walks/places/photos/journeys via just/SQL.  
- **Add-ons:** `just walk-stories` shows major journeys with photos and full-size click without architectural confusion.
