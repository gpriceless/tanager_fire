# Engineering Memory: Tanager Competition

> Long-term memory for Engineering Manager. Tracks architecture, tech debt, and code quality.

**Location:** `/docs/engineering-memory.md`
**Owner:** Engineering Manager (Crenshaw)
**Updated:** 2026-04-27
**Version:** 1.1

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

### Status: Pre-implementation (002-data-pipeline approved)

No code exists yet. The first implementation (002-data-pipeline) will create:

```
tanager/
├── src/tanager/          # Python package
│   ├── __init__.py       # Version, lazy imports
│   ├── config.py         # Sensor params, fire catalog, band aliases, data dir
│   ├── catalog.py        # STAC catalog discovery + download (pystac)
│   ├── io.py             # Tanager HDF5 I/O (HyperCoast wrapper)
│   ├── spectral.py       # Band selection, bad band masking, indices, continuum removal
│   └── masks.py          # No-data, cloud, water, combined masks
├── tests/
│   ├── conftest.py       # Synthetic dataset fixtures (426 bands, known signatures)
│   ├── test_spectral.py  # Band ops, indices, continuum removal tests
│   ├── test_masks.py     # Mask function tests
│   └── test_catalog.py   # STAC catalog tests (mocked HTTP)
├── data/raw/fire/        # Downloaded HDF5 scenes (.h5, gitignored)
├── notebooks/            # Competition deliverables (Phase 4)
└── pyproject.toml        # Package config, deps
```

### Future Modules (Phase 3+)

| Module | Purpose | Phase |
|--------|---------|-------|
| `fire.py` | MESMA burn severity, dNBR classification | Phase 3 |
| `lfmc.py` | Live fuel moisture content estimation (PLSR, indices) | Phase 3 |
| `validation.py` | Cross-validation against AVIRIS-3, BARC, Sentinel-2 | Phase 3 |
| `viz.py` | Visualization helpers (leafmap, matplotlib) | Phase 4 |
| `export.py` | OGC output (GeoPackage, GeoZarr, COG) | Phase 4 |

### Key Dependencies

| Library | Purpose | Version Constraint | Notes |
|---------|---------|-------------------|-------|
| hypercoast | Tanager HDF5 I/O | >=0.22.0,<1.0 | `read_tanager()` — pin below 1.0, API may shift |
| spectral (SPy) | Spectral algorithms | Latest (0.24) | MESMA, SAM, endmember ops (Phase 3) |
| rasterio | Raster I/O | >=1.3 | Geospatial raster handling |
| xarray | N-dim arrays | Latest | Core data structure |
| geopandas | Vector ops | >=0.12 | Output geometries |
| scikit-learn | ML | Latest | PLSR, Random Forest (Phase 3) |
| pystac | STAC catalog | Latest (1.14.3) | Static catalog — NOT pystac-client |
| requests | HTTP | Latest | Scene downloads |
| spyndex | Spectral indices | Latest (0.10.0) | Reference/validation, 232+ indices |
| h5py | HDF5 access | Latest | Raw HDF5 reading (cloud mask, metadata) |
| pytest | Testing | Latest | Dev dependency |
| ruff | Linting | Latest | Dev dependency |
| mypy | Type checking | Latest | Dev dependency |

---

## Architecture Decisions

| Decision | Choice | Rationale | Date |
|----------|--------|-----------|------|
| Data format | xarray for hyperspectral cubes | 426 bands = N-dimensional, xarray is standard | 2026-04-27 |
| I/O layer | HyperCoast wrapper | Already has `read_tanager()`, maintained by opengeos | 2026-04-27 |
| Spectral analysis | SPy (spectral-python) | Mature, MESMA/SAM implementations | 2026-04-27 |
| STAC client | pystac (static) | Planet catalog is static, no /search endpoint | 2026-04-27 |
| HyperCoast pinning | >=0.22.0,<1.0 | Pre-1.0 API instability; research tested 0.20.2, latest 0.22.0 | 2026-04-27 |
| Data directory | data/raw/fire/ + env override | .gitignore coverage, TANAGER_DATA_DIR env var | 2026-04-27 |
| MESMA library | Deferred to Phase 3 | SPy vs mesma v1.0.8 — need empirical 426-band test first | 2026-04-27 |
| Output format | GeoPackage + GeoZarr | OGC-interoperable, cloud-native | 2026-04-27 |
| Notebooks | Jupyter | Competition deliverable format | 2026-04-27 |
| Index computation | Direct implementation, not spyndex | Full control over band selection and NaN handling | 2026-04-27 |
| Cloud mask source | h5py direct HDF5 read | HyperCoast may not expose beta_cirrus_mask field | 2026-04-27 |

---

## Patterns

### Spectral Data Handling
- Always preserve wavelength metadata alongside pixel values
- Use xarray DataArrays with `wavelength` coordinate, not raw numpy
- Wavelengths in nanometers (nm), not micrometers
- Band lookup via `.sel(wavelength=target, method="nearest")` — Tanager's 5nm spacing guarantees <2.5nm error

### Module Import Pattern
- `tanager.config` — static constants, no heavy imports
- `tanager.catalog` — network I/O, isolated from analysis code
- `tanager.io` — HyperCoast wrapper, thin adapter
- `tanager.spectral` — pure computation on xarray, no I/O
- `tanager.masks` — can import from spectral (one-way), never the reverse

### Dependency Direction (ENFORCED)
```
config  <-- catalog
config  <-- io
config  <-- spectral
spectral <-- masks    (water_mask uses ndwi)
```
No circular imports. masks.py may import from spectral.py but NOT vice versa.

### Validation
- Compare against Sentinel-2 dNBR as baseline
- Use known fire perimeters (NIFC) for spatial validation
- Report R2, RMSE, and bias for quantitative comparisons

### Error Handling
- Network errors: raise ConnectionError with URL context
- Invalid files: raise ValueError with filepath context
- Empty results: raise ValueError (e.g., no bands in range)
- Missing metadata: return None or fallback value, log warning (don't error)

---

## Tech Debt Tracking

| ID | Issue | Severity | Status | Notes |
|----|-------|----------|--------|-------|
| TD-1 | Scene count ambiguity (11 vs 12) | Low | Open | Data access eval lists 11, proposal says 12. Resolve at build time via live STAC query. |
| TD-2 | spectral.py may need splitting | Low | Deferred | If spectral.py exceeds ~300 lines in Phase 3, split into spectral/bands.py, spectral/indices.py, spectral/continuum.py |
| TD-3 | HyperCoast wavelength_range loading | Low | Documented | read_tanager() takes band indices, not wavelengths. io.py must translate. |

---

## Known Constraints

### HyperCoast Integration
- `read_tanager()` returns xarray.Dataset with (wavelength, y, x) dims
- `bands` parameter accepts integer indices, not wavelength values
- Only works with Ortho products (Basic products are ungridded — use `grid_tanager()` first)
- beta_cirrus_mask may not be exposed in xarray output — use h5py for raw HDF5 access

### STAC Catalog
- Static catalog, no /search endpoint
- pystac (NOT pystac-client)
- No authentication required
- URL: https://www.planet.com/data/stac/tanager-core-imagery/catalog.json
- Fire collection: catalog.get_child("fire")

### Tanager File Format
- HDF-EOS5 (.h5 extension, not .hdf5)
- Internal path: /HDFEOS/SWATHS/HYP/Data_Fields/surface_reflectance
- Dimensions: [bands, rows, cols] Float32
- ~480 MB per scene per product
- ~2 GB RAM per loaded scene

---

## Recent Changes

| Date | Change | Status |
|------|--------|--------|
| 2026-04-27 | Project initialized | **DONE** |
| 2026-04-27 | 002-data-pipeline reviewed by EM — READY | **DONE** |
