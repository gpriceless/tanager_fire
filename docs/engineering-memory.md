# Engineering Memory: Tanager Competition

> Long-term memory for Engineering Manager. Tracks architecture, tech debt, and code quality.

**Location:** `/docs/engineering-memory.md`
**Owner:** Engineering Manager (Crenshaw)
**Updated:** 2026-04-27
**Version:** 2.0 (002-data-pipeline enrichment)

---

## Purpose

This document is the Engineering Manager's working memory. It tracks:
1. **What exists** — Prevent duplicate implementations
2. **Architecture decisions** — What to use, what to avoid
3. **Tech debt** — Known issues and their status
4. **Patterns** — How things should be done

**All coding agents should check this before building new features.**

---

## Architecture Overview

### Status: Phase 2 — Data Pipeline (002-data-pipeline)

Python package at `src/tanager/`, editable install via `pip install -e .`.

### Module Registry

```
src/tanager/
├── __init__.py       # Package version, lazy public API imports
├── config.py         # Sensor params (SENSOR), bad bands, fire scene catalog, band aliases, DATA_DIR
├── catalog.py        # STAC catalog interface — list, filter, download fire scenes via pystac
├── io.py             # Scene I/O — load HDF5 via HyperCoast read_tanager(), spatial info extraction
├── spectral.py       # Band selection, bad band masking, spectral indices (NBR/NDVI/NDWI/dNBR), continuum removal
└── masks.py          # No-data, cloud/cirrus, water body masking, combined mask application

tests/
├── conftest.py       # Synthetic 426-band xarray.Dataset fixtures with known spectral signatures
├── test_spectral.py  # Band selection, bad bands, indices, continuum removal, div-by-zero
├── test_masks.py     # No-data, cloud, water, combined mask tests
├── test_catalog.py   # STAC browsing/filtering with mocked HTTP
└── test_io.py        # Scene loading with mocked HyperCoast
```

### Key Dependencies

| Library | Purpose | Version Constraint | Notes |
|---------|---------|-------------------|-------|
| HyperCoast | Tanager HDF5 I/O | `>=0.22.0,<1.0` | `read_tanager()` — API may shift pre-1.0 |
| spectral (SPy) | Spectral algorithms | Latest | MESMA, SAM, endmember extraction |
| rasterio | Raster I/O | >=1.3 | Geospatial raster handling |
| xarray | N-dim arrays | Latest | Hyperspectral cube handling |
| geopandas | Vector ops | >=0.12 | Output geometries |
| pystac | STAC catalog | Latest | Static catalog traversal (NOT pystac-client) |
| requests | HTTP downloads | Latest | Scene file downloads, no auth required |
| spyndex | Spectral indices | Latest (0.10.0+) | Reference/validation, not core computation |
| h5py | HDF5 access | Latest | Required for cloud_mask beta_cirrus_mask reading |
| scikit-learn | ML | Latest | For Phase 3 PLSR/RF |
| scipy | Scientific computing | Latest | ConvexHull for continuum removal |

**Dev dependencies:** pytest, ruff, mypy

### Data Convention

- **Default data directory:** `data/raw/fire/` relative to project root
- **Override:** `TANAGER_DATA_DIR` environment variable
- **File extension:** `.h5` (HDF-EOS5), not `.hdf5`
- **Storage:** ~480 MB per scene, ~6 GB for full fire collection (ortho SR only)
- **gitignore:** `data/raw/` glob covers all raw data; explicit `*.h5` also added

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package layout | `src/tanager/` (src layout) | Editable install, clean namespace |
| Data format | xarray for hyperspectral cubes | 426 bands = N-dimensional, xarray is standard |
| I/O layer | HyperCoast `read_tanager()` | Already handles HDF-EOS5 layout discovery |
| STAC access | pystac (static catalog) | No STAC API exists — must use static catalog reader |
| Spectral analysis | SPy (spectral-python) | Mature, MESMA/SAM implementations |
| MESMA software | Deferred to Phase 3 | mesma v1.0.8 is primary candidate; HySUPP fallback. 426-band perf untested. |
| Sensor config | SimpleNamespace (dot notation) | `SENSOR.n_bands` not `SENSOR["n_bands"]` |
| Index computation | Direct band math (not spyndex) | Full control over band selection; spyndex for validation only |
| Continuum removal | scipy ConvexHull | Standard approach; per-pixel via apply_ufunc |
| Output format | GeoPackage + GeoZarr (Phase 4) | OGC-interoperable, cloud-native |
| Notebooks | Jupyter (Phase 4) | Competition deliverable format |
| HyperCoast version | `>=0.22.0,<1.0` | Floor at latest tested; cap at major version boundary |

---

## Patterns

### Spectral Data Handling
- Always preserve wavelength metadata alongside pixel values
- Use xarray DataArrays with `wavelength` coordinate, not raw numpy
- Wavelengths in nanometers (nm), not micrometers
- Band lookup by wavelength uses `method="nearest"` (5nm spacing = max 2.5nm error)

### Import Direction (dependency rule)
- `masks.py` MAY import from `spectral.py` (for ndwi)
- `spectral.py` MUST NOT import from `masks.py` (circular dependency)
- `spectral.py` and `catalog.py` MAY import from `config.py`
- `io.py` is independent (only imports HyperCoast)

### Error Handling
- Division by zero in normalized difference indices: return NaN, never Inf
- Network failures (STAC catalog): catch and re-raise as ConnectionError with URL context
- Invalid HDF5 files: catch and re-raise as ValueError with filepath context
- Missing HDF5 fields (beta_cirrus_mask): log warning, return permissive default (all-True mask)

### Logging
- Use Python `logging` module, never `print()`
- All functions that perform I/O or filtering should log at INFO level
- Warnings for unexpected data shapes or missing fields

### Validation
- Compare against Sentinel-2 dNBR as baseline
- Use known fire perimeters (NIFC) for spatial validation
- Report R2, RMSE, and bias for quantitative comparisons

---

## Tech Debt Tracking

| ID | Issue | Severity | Status |
|----|-------|----------|--------|
| TD-1 | Scene count ambiguity (11 vs 12 fire scenes) | Low | Will resolve at build time via live STAC query |
| TD-2 | HyperCoast wavelength_range: must load-then-slice (no native wavelength filter) | Low | Documented in io.py gotcha |
| TD-3 | cloud_mask may require direct h5py access (HyperCoast may not expose beta_cirrus_mask) | Medium | h5py added as dependency; fallback documented |

---

## Recent Changes

| Date | Change | Status |
|------|--------|--------|
| 2026-04-27 | Project initialized | **DONE** |
| 2026-04-27 | 002-data-pipeline tasks.md enriched (EM audit) | **DONE** |
