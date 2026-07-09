# Change: 005-submission-packaging

## Open Questions — RESOLVED BY EM (2026-07-08)

1. **Notebook execution strategy:** Ship with pre-computed outputs + `Makefile` for clean reproduction.
   <!-- eng-note: RESOLVED — ship with outputs. `make clean && make notebooks` for full repro. -->

2. **Globe-LFMC data bundling:** Bundle SoCal subset (~2 MB) in `data/reference/`.
   <!-- eng-note: RESOLVED — bundle subset for reproducibility. Full DB download documented in NB03. -->

3. **CI scope:** pytest + ruff only. Notebook execution is a manual step documented in README.
   <!-- eng-note: RESOLVED — no notebook execution in CI. conftest.py already handles missing optional deps. -->

4. **Zenodo timing:** Create DOI before submission so the memo can reference a permanent DOI.
   <!-- eng-note: RESOLVED — before submission. Manual step for gpriceless, not automated. -->

5. **Notebook 04 data availability:** TD-7 (pre-fire scene ~60km offset) affects temporal
   trajectory. Dec 15 scene is pre-fire but does not spatially overlap post-fire footprints.
   Notebook must handle this explicitly — compute trajectories over available overlap area only.
   <!-- eng-note: RESOLVED — known limitation. NB04 must use common overlap area and disclose spatial offset. See TD-7 in engineering-memory.md. -->

---

## Wave 1: Repository Packaging & Infrastructure
<!-- execution: sequential -->

### Section 1: Open-Source Packaging
<!-- execution_mode: sequential -->

- [x] Create `LICENSE` file (MIT)
  <!-- files: LICENSE (create) -->
  <!-- acceptance: MIT license text with correct year (2026) and copyright holder -->

- [x] Create `CITATION.cff` with machine-readable citation metadata
  <!-- files: CITATION.cff (create) -->
  <!-- pattern: follow Citation File Format 1.2.0 spec. Include: title (FireSpec), authors,
       repository URL, license, keywords (hyperspectral, wildfire, MESMA, LFMC, Tanager-1) -->
  <!-- acceptance: cff-converter validates without errors -->

- [x] Write `README.md` with installation, quickstart, and results overview
  <!-- files: README.md (create or replace) -->
  <!-- structure:
       1. Title + one-line description + badges (Python, License, Tests)
       2. "Results at a Glance" — 2-3 key figures inlined (burn severity map, temporal trajectory)
       3. "Installation" — pip install, data download
       4. "Quickstart" — 5-line code snippet loading a scene + computing NBR
       5. "Notebooks" — table of 5 notebooks with descriptions
       6. "API Reference" — link to docs/api-reference.md
       7. "Competition" — link to Planet Tanager Open Data Competition
       8. "Citation" — BibTeX snippet
       9. "License" — MIT -->
  <!-- gotcha: README figures reference files in figures/ — these don't exist yet.
       Use placeholder paths; they'll be populated when notebooks are run. -->
  <!-- acceptance: README renders correctly on GitHub with all sections present -->

- [x] Create `.github/workflows/ci.yml` — pytest + ruff CI pipeline
  <!-- files: .github/workflows/ci.yml (create) -->
  <!-- pattern: GitHub Actions workflow, Python 3.12, ubuntu-latest.
       Steps: checkout, setup-python, pip install -e ".[dev]", ruff check, pytest.
       Skip notebook execution. -->
  <!-- gotcha: some tests mock external deps (HyperCoast, mesma). CI should pass without
       real data or optional deps. Check if conftest.py handles missing optional deps. -->
  <!-- acceptance: workflow runs pytest + ruff lint and reports status -->

- [x] Add `notebook` optional-dependencies group to `pyproject.toml`
  <!-- files: pyproject.toml (modify) -->
  <!-- gotcha: dev group ALREADY EXISTS with ["pytest", "ruff", "mypy"]. Do NOT duplicate.
       Only add: notebook = ["jupyter", "nbformat"] extras group.
       Also verify mesma is in optional deps (already present as [mesma]). -->
  <!-- acceptance: pip install -e ".[dev,notebook]" succeeds -->

- [x] Write `docs/api-reference.md` — public API summary with usage examples
  <!-- files: docs/api-reference.md (create) -->
  <!-- structure: one section per module (config, catalog, io, spectral, masks, endmembers,
       unmixing, severity, lfmc, validation, visualization). Each section: function signatures,
       parameter descriptions, one usage example. -->
  <!-- gotcha: keep this maintainable — link to docstrings rather than duplicating.
       Focus on the 15-20 functions a judge would actually call.
       Key exports per __init__.py: 12 visualization, 7 endmembers, 5 spectral, 4 severity,
       4 lfmc, 4 unmixing, 5 validation, 4 masks, 3 catalog, 3 io, 5 config = ~56 total.
       Prioritize: run_mesma, predict_severity, compute_lfmc_indices, predict_lfmc,
       compute_trajectories, compare_sensors, plot_before_after, plot_severity_summary,
       plot_temporal_trajectory, save_figure, load_ortho_scene, list_fire_scenes. -->
  <!-- acceptance: all public API functions from __init__.py listed with examples -->

---

## Wave 2: Jupyter Notebook Suite (Part 1)
<!-- execution: sequential -->
<!-- gate: Wave 1 must pass QA before starting Wave 2 -->

### Section 2: Data Discovery Notebook
<!-- execution_mode: sequential -->

- [x] Create `notebooks/01-data-discovery.ipynb` — STAC catalog traversal and scene inventory
  <!-- files: notebooks/01-data-discovery.ipynb (create) -->
  <!-- structure:
       1. Introduction: Tanager-1 sensor overview, LA wildfire context (Jan 7, 2025 fires)
       2. STAC Discovery: pystac catalog traversal, scene filtering by fire collection
       3. Scene Inventory: table of 8 LA scenes with dates, phases, GSD
       4. Quicklooks: true-color RGB composites for pre-fire (Dec 15) and post-fire (Jan 23)
       5. Spatial Context: map showing scene footprints over LA (using visualization.py if available)
       6. Summary: what the data tells us, what we'll analyze next -->
  <!-- pattern: use tanager.list_fire_scenes(), tanager.download_scene(), tanager.load_ortho_scene().
       Visualization: tanager.plot_map() for RGB quicklooks, tanager.interactive_map() for
       spatial context (HTML Leaflet map of scene footprints). tanager.add_basemap() for
       satellite imagery context. Markdown cells should tell a story — not just show code.
       Aim for ~40% markdown, 60% code. -->
  <!-- gotcha: network access needed for STAC queries. Include a try/except with helpful message
       if catalog is unreachable. Consider caching scene list in a cell output. -->
  <!-- acceptance: notebook executes end-to-end; shows scene table + RGB quicklooks -->

### Section 3: Burn Severity Notebook
<!-- execution_mode: sequential -->

- [x] Create `notebooks/02-burn-severity.ipynb` — MESMA burn severity analysis
  <!-- files: notebooks/02-burn-severity.ipynb (create) -->
  <!-- structure:
       1. Introduction: why hyperspectral for burn severity, MESMA methodology overview
       2. Data Loading: load pre-fire + post-fire scenes, apply masks
       3. Endmember Library: load FRAMES/USGS spectra, resample to Tanager bands, visualize
       4. Spectral Unmixing: run MESMA, display fraction maps (char, PV, NPV, soil)
       5. Severity Mapping: RF training (fractions → CBI), BARC classification
       6. Visualization: before/after comparison, severity map with fire perimeters
       7. Validation: compare against USGS BARC maps, report accuracy metrics
       8. Discussion: interpret results, note synthetic CBI limitation -->
  <!-- pattern: use tanager.run_mesma(), tanager.train_severity_model(),
       tanager.predict_severity(). Returns dict with 'cbi' (continuous [0,3]) and
       'severity_class' (5-class BARC integer). Visualization via tanager.plot_before_after(),
       tanager.plot_severity_summary(fractions, cbi, severity_class). Also available:
       tanager.plot_difference_map() for dNBR, tanager.overlay_perimeters() for fire boundaries,
       tanager.load_fire_perimeters() to load NIFC data. -->
  <!-- gotcha: MESMA on full scene is slow (~10 min). Consider running on a subset
       (e.g., 500×500 crop over burn scar) for notebook interactivity, with note that
       full-scene results are in outputs/. -->
  <!-- gotcha: currently using synthetic CBI (3×char). Be explicit about this in the notebook
       text — transparency strengthens the scientific integrity score. -->
  <!-- gotcha: TD-8 — MESMA fractions violate non-negativity (5-9% negative, 8-12% >1.0
       after shade normalization). normalize_fractions() clamps. Notebook should note this. -->
  <!-- gotcha: TD-7 — pre-fire scene (Dec 15) is ~60km from post-fire footprint. dNBR may use
       different spatial extents. plot_before_after() handles different extents per panel. -->
  <!-- acceptance: notebook produces fraction maps, severity classification, and validation metrics -->

### Section 4: Fuel Moisture Notebook
<!-- execution_mode: sequential -->

- [x] Create `notebooks/03-fuel-moisture.ipynb` — LFMC estimation pipeline
  <!-- files: notebooks/03-fuel-moisture.ipynb (create) -->
  <!-- structure:
       1. Introduction: LFMC importance for wildfire risk, hyperspectral advantage
       2. Spectral Water Indices: compute SAI970, SAI1200, NDWI variants, visualize
       3. Continuum Removal: band depth at 970, 1200, 2100 nm water absorption features
       4. PLSR Regression: train on Globe-LFMC data, cross-validation, feature importance
       5. Per-Pixel LFMC Map: predict moisture with uncertainty, threshold for fire danger
       6. Discussion: first satellite hyperspectral LFMC product, limitations, operational context -->
  <!-- pattern: use tanager.compute_lfmc_indices(), tanager.predict_lfmc().
       Also: tanager.load_globe_lfmc() for training data, tanager.train_lfmc_plsr() for model.
       Show individual index maps before PLSR composite for pedagogical value.
       Visualization: tanager.plot_map(da, product_name="lfmc") for per-pixel maps. -->
  <!-- gotcha: PLSR training requires Globe-LFMC data. If not available locally,
       include a download cell or document the acquisition step. -->
  <!-- gotcha: TD-11 — continuum removal too slow for full scenes (>4min killed). Only 256×256
       crops work. Notebook should use a crop for CR-based features, note limitation. -->
  <!-- gotcha: TD-9 — SAI1660 produces all zeros on real Tanager data (atmospheric absorption
       at 1530-1790nm). Exclude from feature set or note as limitation. -->
  <!-- acceptance: notebook produces LFMC index maps and per-pixel moisture prediction -->

---

## Wave 3: Jupyter Notebook Suite (Part 2)
<!-- execution: sequential -->
<!-- gate: Wave 2 must pass QA before starting Wave 3 -->

### Section 5: Temporal Recovery Notebook
<!-- execution_mode: sequential -->

- [x] Create `notebooks/04-temporal-recovery.ipynb` — multi-temporal trajectory analysis
  <!-- files: notebooks/04-temporal-recovery.ipynb (create) -->
  <!-- structure:
       1. Introduction: temporal monitoring value, 7-date Tanager time series
       2. Multi-Date Loading: load scenes from 5+ dates, compute indices per date
       3. Temporal Trajectories: NBR, NDVI, LFMC evolution over time with fire event marker
       4. Recovery by Severity: stratify trajectory by BARC severity class
       5. Recovery Rate Quantification: slope of recovery, time-to-baseline estimates
       6. Discussion: ecological interpretation, recovery monitoring for land management -->
  <!-- pattern: use tanager.compute_trajectories() for trajectory data.
       Plot with tanager.plot_temporal_trajectory(dates, values, product_name, fire_date="2025-01-07").
       Signature: (dates, values, product_name, fire_date, error_bands, publication).
       Returns Figure. fire_date adds a red dashed vertical line. -->
  <!-- gotcha: requires scenes from multiple dates to be downloaded and loadable.
       At minimum need Dec 15, Jan 23, Apr 7 for a meaningful trajectory.
       Jul and Sep scenes strengthen the story but may not be available. -->
  <!-- gotcha: scenes from different dates have different spatial extents — must compute
       trajectories over the common overlap area only. -->
  <!-- acceptance: notebook shows temporal trajectory charts with fire event marker and recovery phases -->

### Section 6: Sensor Comparison Notebook
<!-- execution_mode: sequential -->

- [x] Create `notebooks/05-sensor-comparison.ipynb` — Tanager spectral advantage quantification
  <!-- files: notebooks/05-sensor-comparison.ipynb (create) -->
  <!-- structure:
       1. Introduction: why spectral resolution matters, Tanager vs competitors
       2. Sensor Specs: comparison table (Tanager, EMIT, PRISMA, Sentinel-2)
       3. Spectral Degradation: simulate each sensor from Tanager data using BandResampler
       4. Index Comparison: NBR, NDVI computed at each spectral resolution
       5. MESMA Comparison: fraction accuracy at each resolution (if feasible)
       6. Quantification: improvement ratios, information loss curves
       7. Discussion: when hyperspectral matters most, operational implications -->
  <!-- pattern: use tanager.simulate_sensor(), tanager.compare_sensors().
       simulate_sensor() returns degraded xr.Dataset. compare_sensors() returns dict with
       improvement_ratios + comparison_table. Show spectral response functions before and after
       degradation. tanager.resample_library() for each simulated sensor's endmember library. -->
  <!-- gotcha: MESMA at degraded resolution may require different endmember libraries
       (resampled to target bands). Use tanager.resample_library() for each simulated sensor. -->
  <!-- acceptance: notebook produces comparison table and improvement ratio figure -->

---

## Wave 4: Technical Memo & Final Polish
<!-- execution: sequential -->
<!-- gate: Wave 3 must pass QA before starting Wave 4 -->

### Section 7: Technical Memo
<!-- execution_mode: sequential -->

- [x] Write `docs/technical-memo.md` — competition technical memo (1-3 pages)
  <!-- files: docs/technical-memo.md (create) -->
  <!-- structure:
       Abstract (100 words), Introduction (problem + approach), Methodology (MESMA, LFMC, temporal),
       Results (key metrics from notebooks), Discussion (significance, limitations, future work),
       References -->
  <!-- content: synthesize results from notebooks 02-05. Key metrics to include:
       - CBI R² and RMSE vs BARC
       - LFMC estimation accuracy
       - Temporal recovery quantification
       - Tanager improvement ratios vs EMIT/PRISMA/S2
       Note: exact numbers come from notebook outputs — use placeholders if notebooks
       haven't been run yet, to be filled in during final polish. -->
  <!-- acceptance: memo is under 3 pages when rendered, contains all required sections -->

### Section 8: Figure Export & Submission Artifacts
<!-- execution_mode: sequential -->

- [x] Export publication figures from notebooks to `figures/` directory
  <!-- files: figures/ (create directory + PNG files) -->
  <!-- pattern: tanager.save_figure(fig, "figures/name", ["png"]) — already defaults to 300 DPI.
       Signature: save_figure(fig, path, formats=["png"]). path is base WITHOUT extension.
       Creates parent dirs automatically. Minimum set: rgb_pre_post.png, severity_summary.png,
       severity_map.png, lfmc_map.png, temporal_trajectory.png, sensor_comparison.png -->
  <!-- acceptance: figures/ contains 6+ PNG files at 300 DPI -->

- [x] Create `Makefile` with notebook execution and figure export targets
  <!-- files: Makefile (create) -->
  <!-- targets:
       install: pip install -e ".[dev,notebook]"
       test: pytest
       lint: ruff check
       notebooks: jupyter nbconvert --execute notebooks/*.ipynb
       figures: extract figures from executed notebooks
       clean: remove notebook outputs and figures
       all: install test lint notebooks figures -->
  <!-- acceptance: make test and make lint succeed -->

- [x] Update `.gitignore` for notebook outputs and large data files
  <!-- files: .gitignore (modify) -->
  <!-- gotcha: ALREADY PRESENT: .ipynb_checkpoints/, *.tif, *.tiff, data/raw/*.
       Only need to ADD: data/reference/*.db (if Globe-LFMC subset is large),
       outputs/ exception rules (track outputs/*.md but not outputs/*.tif — *.tif already global).
       Verify outputs/ directory is selectively tracked. -->
  <!-- acceptance: git status shows no unintended tracked files -->

- [x] Final README polish — insert actual figure paths and results summary
  <!-- files: README.md (modify) -->
  <!-- update: replace placeholder figure paths with actual figures/ paths.
       Add actual R², RMSE numbers from notebook results to "Results at a Glance" section. -->
  <!-- acceptance: README renders with actual figures and metrics -->

---

## Summary

| Wave | Sections | Tasks | Focus |
|------|----------|-------|-------|
| 1 | 1 | 6 | LICENSE, README, CI, API docs, pyproject.toml |
| 2 | 2-4 | 3 | Notebooks 01-03 (data discovery, severity, moisture) |
| 3 | 5-6 | 2 | Notebooks 04-05 (temporal recovery, sensor comparison) |
| 4 | 7-8 | 4 | Technical memo, figure export, Makefile, final polish |
| **Total** | **8** | **16** | |

### Smoke
<!-- execution_mode: sequential -->

- [ ] 8.4 smoke: end-to-end exercise
  <!-- files: all notebooks, outputs/, figures/ -->
  <!-- acceptance: pip install -e ".[dev,notebook]" + pytest passes + at least 1 notebook renders -->
