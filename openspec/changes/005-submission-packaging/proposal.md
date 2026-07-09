# Change: Submission Packaging — Jupyter Notebooks, Technical Memo, Open-Source Release

**Change ID:** 005-submission-packaging
**Plane Issue:** TBD (created by /run-phase)
**Status:** Proposed
**Author:** Product Queen
**Date:** 2026-05-10

---

## Why

We have a complete analysis pipeline — MESMA burn severity, LFMC estimation, sensor comparison,
and (soon) publication-quality visualization. But the competition judges don't evaluate Python
modules. They evaluate **notebooks, figures, narratives, and reproducibility**.

The judging criteria allocate 50 out of 100 points to presentation-adjacent categories:
- **Application or Use Case** (30 pts): relevance, feasibility, real-world impact
- **Workflow & Tool Development** (20 pts): clean code, reproducibility, STAC usage, open-source

Plus two tie-breakers we can claim:
- **Open-source / AI-ML** (+5 pts): new library or cutting-edge AI/ML
- **Planet verticals** (+5 pts): wildfire = eligible

Right now our submission materials are: zero notebooks, no technical memo, no README, no LICENSE,
no Zenodo archive. The code works but isn't packaged for external consumption or competition review.

This phase transforms the codebase into a submission-ready package that a judge can clone, install,
and reproduce in under 30 minutes.

## What Changes

### New: Jupyter Notebook Suite (`notebooks/`)

Five notebooks forming a narrative arc from data discovery through analysis to operational insight:

1. **01-data-discovery.ipynb** — STAC catalog traversal, scene inventory, quicklook mosaics.
   Demonstrates Tanager-1 data access and the LA wildfire time series. Heavy on STAC integration
   (judges value this). Establishes the scientific context: 2025 LA fires, 7 temporal phases.

2. **02-burn-severity.ipynb** — End-to-end burn severity analysis. Endmember library construction,
   MESMA spectral unmixing, CBI estimation, BARC classification. Includes validation against
   AVIRIS-3 fractions (aggregated to 30m) and USGS BARC maps. Key figure: before/after severity
   comparison with fire perimeters.

3. **03-fuel-moisture.ipynb** — LFMC estimation pipeline. Spectral water indices (SAI970, SAI1200,
   NDWI variants, continuum removal depths), PLSR regression, per-pixel moisture maps with
   uncertainty. Contextualizes fuel moisture for wildfire risk assessment.

4. **04-temporal-recovery.ipynb** — Multi-temporal trajectory analysis across 7 scene dates.
   NBR/NDVI/LFMC recovery curves, fire event markers, vegetation regrowth monitoring. This is
   FireSpec's signature differentiator — no other competition entry will have 7-date trajectories.

5. **05-sensor-comparison.ipynb** — Tanager vs EMIT/PRISMA/Sentinel-2 spectral degradation
   simulation. Quantifies the advantage of 426 bands at 5nm vs coarser instruments. Key for +5
   tie-breaker points.

### New: Technical Memo (`docs/technical-memo.md`)

1-3 page structured document (competition requirement) covering:
- Methodology overview (MESMA + LFMC + temporal trajectory)
- Key results with quantitative metrics
- Tanager-1 sensor advantages demonstrated
- Limitations and future work
- References to notebooks for details

### New: Open-Source Packaging

- **README.md** — installation, quickstart, API overview, reproducibility instructions
- **LICENSE** — MIT (compatible with all dependencies)
- **CITATION.cff** — machine-readable citation metadata
- **docs/api-reference.md** — public API summary with usage examples
- **.github/workflows/ci.yml** — CI pipeline (pytest + ruff) for credibility

### Modified: Competition Submission Artifacts

- **figures/** — curated publication-quality PNGs exported from notebooks
- **outputs/** — key GeoTIFF products (severity map, LFMC map, sensor comparison)
- **data/reference/** — NIFC fire perimeters, Globe-LFMC SoCal subset (small files only)

## Impact

- **New files:** 5 notebooks, technical memo, README, LICENSE, CITATION.cff, CI config, API docs
- **Modified files:** pyproject.toml (add notebook deps: jupyter, nbformat), .gitignore (notebook outputs)
- **No changes to existing analysis modules** — notebooks consume existing `tanager` API
- **Dependency on 004-visualization-overhaul:** Notebooks use visualization functions for all figures.
  If 004 is not complete, notebooks can use basic matplotlib fallbacks, but the result will be
  weaker on the Visualization & Storytelling criterion.

## Dependencies on Existing Code

| Module | What Notebooks Use | Notes |
|--------|-------------------|-------|
| `catalog.py` | `list_fire_scenes()`, `download_scene()` | NB01 data discovery |
| `io.py` | `load_ortho_scene()`, `get_spatial_info()` | All notebooks |
| `spectral.py` | `compute_index()`, `dnbr()`, `continuum_removal()` | NB02, NB03 |
| `endmembers.py` | `load_usgs_library()`, `resample_library()` | NB02 |
| `unmixing.py` | `run_mesma()`, `normalize_fractions()` | NB02 |
| `severity.py` | `train_severity_model()`, `classify_severity()`, `compute_trajectories()` | NB02, NB04 |
| `lfmc.py` | `compute_lfmc_indices()`, `predict_lfmc()` | NB03 |
| `validation.py` | `compute_accuracy()`, `compare_sensors()`, `simulate_sensor()` | NB02, NB05 |
| `visualization.py` | All plotting functions (from 004) | All notebooks |

## Research Summary

No new research needed. This phase packages existing analysis into competition-ready format.

Notebook narrative structure follows the "question → method → result → insight" pattern used
in winning entries from prior Planet competitions (e.g., Forest Carbon Diligence Prize 2023:
3 notebooks, STAC-first, progressive complexity, clear operational framing).

## Production Risk

Not applicable — research project.

## Open Questions for EM

1. **Notebook execution time:** Full MESMA on 500K+ pixels takes ~10 min. Should notebooks include
   pre-computed results (faster review) or execute from scratch (reproducibility)? Recommend:
   ship with outputs, include `make clean && make notebooks` for full reproduction.

2. **Globe-LFMC data bundling:** The full Globe-LFMC database is ~50 MB. Should we bundle a SoCal
   subset (~2 MB) in `data/reference/` or document the download in the notebook? Recommend:
   bundle subset for reproducibility.

3. **CI scope:** Should CI run notebooks end-to-end (slow, needs data) or just pytest + lint?
   Recommend: pytest + ruff only in CI; notebook execution documented as manual step.

4. **README depth:** Competition judges may skim. Recommend: structured README with badges,
   quickstart (5 lines), and a "Results at a Glance" section with key figures inlined.

5. **Zenodo archival:** Should we create a Zenodo DOI before or after submission? Before gives
   us a citable DOI in the memo. After is simpler. Recommend: before, to include in memo.
