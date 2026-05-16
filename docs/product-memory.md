# Product Memory: Tanager Competition

> Long-term memory for Product Queen. Tracks product evolution, research synthesis, and competition strategy.

**Location:** `/docs/product-memory.md`
**Owner:** Product Queen
**Updated:** 2026-04-27
**Version:** 2.1

---

## Executive Summary

Tanager Competition is a research project targeting the Planet Tanager Open Data Competition (deadline: August 31, 2026). We are building a wildfire-focused hyperspectral analysis toolkit using Tanager-1's 426-band imagery. The deliverable is an open-source, OGC-interoperable submission demonstrating burn severity mapping and live fuel moisture estimation.

---

## Current State

**Last Updated:** 2026-05-10
**Current Phase:** Phase 3 COMPLETE + all science bugs fixed. Visualization Overhaul (004-visualization-overhaul) specced, awaiting EM enrichment. Phase 4 not yet specced.

### What Exists
| Capability | Status | Key Details |
|-----------|--------|-------------|
| Prior Research | Complete | Competition analysis + deep research |
| Literature Review | Complete | MESMA burn severity + PLSR LFMC methodology validated |
| Data Access Research | Complete | STAC catalog, HyperCoast I/O, scene inventory confirmed |
| Project Setup | Complete | OpenSpec, memory system, pyproject.toml, editable install |
| Data Pipeline (code) | **Complete** | 41/41 tasks, 159 tests passing. Modules: config, catalog, io, spectral, masks |
| Core Analysis | **Complete** | 55/55 tasks, 334 tests passing. Modules: endmembers, unmixing, severity, lfmc, validation. Phase gate passed 2026-04-28. |
| Science Bug Fixes | **Complete** | All 6 validation bugs (TD-7 through TD-12) resolved. dNBR temporal fix, MESMA fraction clamping, SAI1660 removed, SAI NaN fix, CBI/BARC naming fix, LFMC full-scene. |
| Sensor Comparison | **Complete** | Spectral degradation simulation (Tanager→EMIT/PRISMA/S2) via simulate_sensor() + stage_sensor_comparison(). +5 tie-breaker. |
| Visualization Overhaul | **Specced** | OpenSpec 004-visualization-overhaul proposed. 24 tasks, 4 waves, 1 new module (visualization.py). Awaiting EM enrichment. |
| Packaging & Submission | **Specced** | OpenSpec 005-submission-packaging proposed. 15 tasks, 4 waves, 5 notebooks + memo + open-source packaging. Awaiting EM enrichment. |

### Remaining Gaps
- No geographic visualization (pixel coords only, no basemaps/perimeters) — 004-visualization-overhaul addresses this
- No Jupyter notebook structure (Phase 4)
- No NIFC fire perimeter data acquired yet
- Competition track not formally selected (but FireSpec direction confirmed)
- No open-source packaging (README, Zenodo, pip installable) — Phase 4

---

## Research Findings

### Phase 1 Research (Complete)

**Literature Review** (Tobler, 2026-04-27):
- MESMA with Char/PV/NPVS endmembers is proven: PRISMA R²=0.79 vs Sentinel-2 R²=0.46 (Quintano 2023)
- Tanager's 426 bands at ~5nm should equal or exceed PRISMA's 240 bands at ~12nm
- PLSR achieves R²=0.72-0.94 for LFMC at leaf level
- Key wavelengths: 970nm, 1200nm (water), 1680nm (lignin), 2100nm, 2280nm (cellulose)
- Atmospheric exclusion zones: 1345-1459nm, 1774-1975nm, 2469-2505nm
- 7-scene temporal trajectory is FireSpec's signature differentiator
- Target accuracy: R²>0.70 CBI, RMSE<20% FMC

**Data Access Evaluation** (Tobler, 2026-04-27):
- Static STAC catalog, no auth: `planet.com/data/stac/tanager-core-imagery/catalog.json`
- Use `pystac` (NOT pystac-client) for static catalog
- HDF-EOS5 format, HyperCoast `read_tanager()` → xarray.Dataset
- 11 fire scenes (confirmed): pre-fire (Dec 15), post-fire (Jan 23), recovery (Apr, Jul, Sep)
- Ortho Surface Reflectance is primary product (~480 MB/scene)

**Endmember Library Research** (Tobler, 2026-04-27):
- FRAMES SoCal chaparral: 66 spectra (7 char/ash, 36 GV, 13 NPV, 10 soil) from Old Fire + Simi Fire
- USGS v7: char/charcoal, heated soils, chaparral vegetation
- ECOSTRESS: 541 vegetation + 51 NPV spectra (VSWIR)
- Strategy: hybrid library with In-CoB + EAR/MASA selection → ~52-78 final spectra
- Tools: spectral-libraries v1.1.3 (EarMasaCob), splib07-loader, SPy BandResampler

### 6 Project Ideas (Tobler, April 2026)

1. **TanagerFlow** — OGC-interoperable hyperspectral analysis toolkit (8-10 wk)
2. **SpectralMiner** — Mineral mapping with USGS Spectral Library v7 (8-10 wk)
3. **HyperWater** — Water quality pipeline (HAB detection, Chl-a) (8-10 wk)
4. **CarbonSpec** — Soil organic carbon mapping (10-12 wk)
5. **FireSpec** — Live fuel moisture + post-fire burn severity (6-8 wk) ← **SELECTED**
6. **CoastalSpec** — Land-water coastal ecosystem assessment (8-10 wk)

### Why FireSpec
- Published evidence: 2x better R² than Sentinel-2 dNBR for burn severity
- LA wildfire time series (7 Tanager scenes, Dec 2024 – Jul 2025) provides compelling case study
- Timely, fundable, operationally relevant to wildfire agencies
- 6-8 week estimate fits competition timeline with room for depth

---

## Roadmap

| Phase | Focus | Timeline | Status |
|-------|-------|----------|--------|
| 1 | Foundation & Literature Review | Apr 2026 | **Complete** |
| 2 | Data Pipeline & Project Scaffolding | Apr 2026 | **Complete** (41/41 tasks, 159 tests) |
| 3 | Core Analysis (MESMA, LFMC) | Apr 2026 | **Complete** (55/55 tasks, 334 tests, phase gate passed) |
| 3.1 | Science Bug Fixes + Sensor Comparison | May 2026 | **Complete** (6 bugs fixed, sensor degradation simulation shipped) |
| 3.5 | Visualization Overhaul | May 2026 | **Specced** (004-visualization-overhaul, 24 tasks, 4 waves) |
| 4 | Packaging & Submission | Jun-Aug 2026 | **Specced** (005-submission-packaging, 15 tasks, 4 waves) |

---

## Recent Activity

| Date | Event | Details |
|------|-------|---------|
| 2026-05-10 | Phase 4 specced | OpenSpec 005-submission-packaging: 5 Jupyter notebooks, technical memo, README, LICENSE, CITATION.cff, CI pipeline, API docs, figure export. 15 tasks, 4 waves. Awaiting EM enrichment. |
| 2026-05-10 | Product memory updated, Plane synced | TANAGER-27 through TANAGER-34 closed (all had commits on main). Product memory updated with bug fix and sensor comparison status. |
| 2026-05-10 | All science bugs resolved | 6/6 validation issues fixed: dNBR pre→post overlap (f7e2754), MESMA fraction clamp (6c3f864), SAI NaN (02b354e), SAI1660 dropped (86af154), CBI/BARC labeling (10c9e83), LFMC full-scene (cc364fe). |
| 2026-05-10 | Sensor comparison shipped | simulate_sensor() + stage_sensor_comparison() — spectral degradation simulation Tanager→EMIT/PRISMA/S2 for +5 tie-breaker. Commits c028d67, f28dc55. |
| 2026-05-04 | Visualization overhaul specced | OpenSpec 004-visualization-overhaul: geographic basemaps, fire perimeters, before/after panels, temporal trajectories, publication-quality figures. 24 tasks, 4 waves. +8-12 competition points. |
| 2026-05-04 | Science issues triaged | Tobler triaged 6 P0-P2 issues from validation analysis (LGT-397): dNBR temporal logic, MESMA fraction violations, SAI1660, LFMC crop-only, severity naming, SAI NaN handling. |
| 2026-04-28 | Phase 3 COMPLETE | 55/55 tasks, 334 tests passing. Phase gate passed. All core analysis modules shipped. |
| 2026-04-28 | Phase 3 spec finalized | Incorporated Phase 2 remediation findings: per-band FWHM, reproject_to_common_grid, reflectance clamping, scene overlap warnings. Ready for /run-phase. |
| 2026-04-27 | Phase 3 spec proposed | OpenSpec 003-core-analysis: MESMA + LFMC + severity + validation |
| 2026-04-27 | Phase 2 complete | 41/41 tasks done, 159 tests passing, all modules shipped |
| 2026-04-27 | Phase 1 research complete | Literature review + data access evaluation finished |
| 2026-04-27 | Phase 2 spec proposed | OpenSpec change 002-data-pipeline created, TANAGER-5 |
| 2026-04-27 | Project initialized | OpenSpec, memory system, and research infrastructure set up |
| 2026-04-27 | FireSpec selected | Board chose wildfire focus from 6 candidates |

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-27 | Phase 3 uses mesma v1.0.8 with HySUPP fallback | mesma is proven but old; HySUPP provides safety net |
| 2026-04-27 | Hybrid endmember library strategy | FRAMES primary + USGS + ECOSTRESS + image-derived covers all cases |
| 2026-04-27 | LFMC Tier 1 + Tier 2 only (defer RTM) | Indices + PLSR sufficient for competition; RTM is overengineered |
| 2026-04-27 | Random Forest for severity regression | Handles nonlinear fraction→CBI relationship; proven in literature |
| 2026-04-27 | Focus on FireSpec (wildfire) | Board direction + timely case study + OGC gap |
| 2026-04-27 | Separate project from detr_geo | Different sensor, different tech stack, different deliverable |
| 2026-04-27 | Use HyperCoast for I/O, SPy for spectral | Research evaluation: HyperCoast handles Tanager format, SPy is mature for analysis |
| 2026-04-27 | Static STAC + pystac (not pystac-client) | Data access research confirmed static catalog, no API available |
| 2026-04-27 | Ortho SR as primary product | Pre-corrected by Planet (ISOFIT v2.9.5), no additional atm correction needed |
| 2026-05-10 | Submit under "Code & Scripts" track | Reusable toolkit format maximizes Workflow & Tool Development (20 pts) + open-source tie-breaker (+5); scientific depth still scores on Scientific Integrity (30 pts) |
| 2026-05-10 | Spectral degradation as primary sensor comparison | Convolve Tanager 426 bands to simulate EMIT/PRISMA/S2; isolates spectral resolution advantage from spatial/temporal confounds. Already implemented (commits c028d67, f28dc55). |

---

## Open Threads

1. ~~**mesma v1.0.8 compatibility**~~ — **RESOLVED:** Confirmed working on Python 3.12.3 / numpy 2.4.4.
2. ~~**FRAMES SoCal library acquisition**~~ — **RESOLVED:** Individual ASCII downloads; loader handles local dir.
3. ~~**Globe-LFMC SoCal coverage**~~ — **RESOLVED:** Strong SoCal coverage. Varga & Jones (2026) supplementary source.
4. ~~**AVIRIS-3 Eaton Fire access**~~ — **RESOLVED:** Publicly available at ORNL DAAC.
5. ~~**Competition track selection**~~ — **RESOLVED (2026-05-10):** Submit under **Code & Scripts**. Our deliverables (open-source Python package + 5 Jupyter notebooks + technical memo + GitHub repo) are a reusable toolkit, not a one-off case study. Code & Scripts maximizes Workflow & Tool Development (20 pts) and open-source tie-breaker (+5), while the scientific depth still scores on Scientific Integrity (30 pts).
6. **Field CBI data** — No field CBI for LA fires. Pipeline uses synthetic CBI (3×char), now labeled as synthetic (commit 10c9e83). RAVG data from USGS Burn Severity Portal is best available proxy.
7. **Ash vs. char separation** — Only 7 combined spectra in FRAMES; may need supplementary measurements.
8. **NIFC fire perimeter acquisition** — Required for 004-visualization-overhaul. Two sources identified: (a) NIFC Open Data at data-nifc.opendata.arcgis.com — WFIGS fire perimeters, GeoJSON download, covers all 2025 fires nationally; (b) LA County ArcGIS Hub at egis-lacounty.hub.arcgis.com — local LA perimeters (Palisades, Eaton, Hughes). Recommend: try LA County first (authoritative for our study area), fall back to NIFC national. Download once, bundle in `data/reference/fire_perimeters/`. **Needs human action** — exact URLs need browser verification and manual download.
9. ~~**Phase 4 spec**~~ — **RESOLVED (2026-05-10):** OpenSpec 005-submission-packaging proposed. 15 tasks, 4 waves. Awaiting EM enrichment.
