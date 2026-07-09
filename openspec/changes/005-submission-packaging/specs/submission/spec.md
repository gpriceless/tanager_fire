# Capability: Submission Packaging — Notebooks, Memo, Open-Source Release

**Capability ID:** submission
**Version:** 1.0.0
**Change:** 005-submission-packaging
**Date:** 2026-05-10

---

## Overview

This capability packages the Tanager FireSpec pipeline into competition-ready artifacts: a
5-notebook Jupyter suite, a technical memo, open-source repository packaging, and curated
output figures. The deliverables target the Planet Tanager Open Data Competition judging
criteria (100 pts + 15 tie-breaker).

---

## ADDED Requirements

### Requirement: Data Discovery Notebook

The submission SHALL include a Jupyter notebook (`notebooks/01-data-discovery.ipynb`) that
demonstrates Tanager-1 STAC catalog access and scene inventory for the LA wildfire time series.

#### Scenario: STAC catalog traversal

WHEN the notebook is executed with network access
THEN it SHALL traverse the Planet STAC catalog using pystac
AND display a table of available fire scenes with dates, IDs, and spatial coverage
AND produce quicklook RGB composites for at least the pre-fire and post-fire scenes

#### Scenario: Scene metadata display

WHEN the notebook renders scene metadata
THEN it SHALL show sensor parameters (bands, GSD, wavelength range)
AND display the temporal coverage of the fire collection (7 dates, Dec 2024 – Sep 2025)
AND include a map showing scene footprints over the LA study area

---

### Requirement: Burn Severity Notebook

The submission SHALL include a Jupyter notebook (`notebooks/02-burn-severity.ipynb`) that
demonstrates end-to-end burn severity mapping using MESMA spectral unmixing.

#### Scenario: MESMA burn severity pipeline

WHEN the notebook is executed with pre-fire and post-fire scenes loaded
THEN it SHALL construct a hybrid endmember library (FRAMES + USGS + ECOSTRESS)
AND run MESMA spectral unmixing to produce fraction maps (char, PV, NPV, soil)
AND train a Random Forest model mapping fractions to CBI
AND classify burn severity into BARC categories

#### Scenario: Validation against reference data

WHEN validation cells are executed
THEN the notebook SHALL compare CBI predictions against USGS BARC maps
AND report accuracy metrics (R², RMSE, Cohen's kappa)
AND produce a before/after comparison figure with fire perimeters

---

### Requirement: Fuel Moisture Notebook

The submission SHALL include a Jupyter notebook (`notebooks/03-fuel-moisture.ipynb`) that
demonstrates LFMC estimation from hyperspectral signatures.

#### Scenario: LFMC estimation pipeline

WHEN the notebook is executed with a loaded scene
THEN it SHALL compute spectral water indices (SAI970, SAI1200, NDWI variants)
AND perform continuum removal at diagnostic absorption features
AND train PLSR regression for per-pixel LFMC estimation
AND produce a moisture map with uncertainty bands

#### Scenario: Wildfire risk context

WHEN the notebook presents LFMC results
THEN it SHALL contextualize moisture values against fire danger thresholds
AND explain the operational relevance for pre-fire fuel assessment

---

### Requirement: Temporal Recovery Notebook

The submission SHALL include a Jupyter notebook (`notebooks/04-temporal-recovery.ipynb`) that
demonstrates multi-temporal vegetation recovery monitoring.

#### Scenario: 7-date temporal trajectory

WHEN the notebook is executed with scenes from multiple dates
THEN it SHALL compute NBR, NDVI, and LFMC indices for each available date
AND produce temporal trajectory charts with fire event markers and error bands
AND quantify recovery rates across the burn scar

#### Scenario: Recovery narrative

WHEN the notebook presents temporal results
THEN it SHALL annotate the trajectory with ecological phases (impact, early recovery, regrowth)
AND compare recovery rates between severity classes

---

### Requirement: Sensor Comparison Notebook

The submission SHALL include a Jupyter notebook (`notebooks/05-sensor-comparison.ipynb`) that
quantifies Tanager-1's spectral advantage over coarser instruments.

#### Scenario: Spectral degradation simulation

WHEN the notebook is executed
THEN it SHALL simulate EMIT (285 bands, 7.4nm), PRISMA (239 bands, 12nm),
and Sentinel-2 (13 discrete bands) from Tanager data using spectral convolution
AND run NBR/MESMA/LFMC on each simulated dataset
AND produce a comparison table with accuracy metrics per sensor

#### Scenario: Advantage quantification

WHEN the comparison is complete
THEN the notebook SHALL report improvement ratios (Tanager vs each sensor)
AND produce a figure showing information loss with decreasing spectral resolution

---

### Requirement: Technical Memo

The submission SHALL include a technical memo (`docs/technical-memo.md`) of 1-3 pages covering
methodology, key results, and significance.

#### Scenario: Memo structure

WHEN the memo is rendered
THEN it SHALL contain sections: Abstract, Methodology, Results, Discussion, References
AND cite quantitative metrics from the analysis (R², RMSE, improvement ratios)
AND reference specific notebooks for detailed procedures
AND fit within 3 pages when printed at standard formatting

---

### Requirement: Open-Source Repository Packaging

The submission SHALL include repository artifacts enabling external reproduction and citation.

#### Scenario: README quickstart

WHEN a judge clones the repository
THEN the README SHALL provide installation instructions (pip install + data download)
AND a quickstart section showing how to run the first notebook in under 5 commands
AND a "Results at a Glance" section with key figures

#### Scenario: License and citation

WHEN the repository is published
THEN it SHALL include an MIT LICENSE file
AND a CITATION.cff file with machine-readable citation metadata

#### Scenario: CI pipeline

WHEN code is pushed to the repository
THEN a GitHub Actions workflow SHALL run pytest and ruff lint
AND report pass/fail status

---

### Requirement: Curated Output Figures

The submission SHALL include a `figures/` directory with publication-quality PNG exports
from the notebooks.

#### Scenario: Competition figure set

WHEN figures are exported from the notebooks
THEN the directory SHALL contain at minimum:
- True-color RGB composite (pre-fire and post-fire)
- MESMA fraction summary (6-panel grid)
- Burn severity classification map with fire perimeters
- LFMC moisture map
- Temporal recovery trajectory chart
- Sensor comparison improvement chart
AND all figures SHALL be at 300 DPI with geographic coordinates

---

## Module Public API

This change does not add new Python modules. It creates notebooks that consume the existing
`tanager` package API and adds repository-level packaging files.

---

## Dependencies

| Package | Purpose | New? |
|---------|---------|------|
| jupyter | Notebook execution | **YES** (dev dependency) |
| nbformat | Notebook validation | **YES** (dev dependency) |
| All existing tanager deps | Analysis pipeline | No |

---

## Notebook Dependency Chain

```
01-data-discovery   (standalone — STAC + I/O only)
02-burn-severity    (depends on loaded scenes, endmember library)
03-fuel-moisture    (depends on loaded scenes)
04-temporal-recovery (depends on scenes from multiple dates)
05-sensor-comparison (depends on loaded scene + simulate_sensor)
```

All notebooks depend on `004-visualization-overhaul` for publication-quality figures.
Fallback: basic matplotlib if visualization module is not yet available.
