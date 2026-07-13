# Phase 2 Pipeline — Scientific Defensibility Review

**Date:** 2026-04-27
**Verdict:** **NOT DEFENSIBLE — 4 blocking issues must be resolved**

---

## Executive Summary

The Phase 2 data pipeline (002-data-pipeline) was built to 41/41 tasks with 159 passing tests. However, **all tests use synthetic fixtures with clean, well-behaved data.** Zero real Tanager satellite data had been downloaded or tested until this review.

This review downloaded 3 real ortho surface reflectance scenes (pre-fire, post-fire, recovery) totaling ~3.4 GB and ran the full pipeline against them. The results reveal **4 P0/P1 blocking issues** that make the pipeline non-functional on real data, plus **9 additional issues** ranging from incorrect metadata to missing capabilities.

The pipeline's architecture is sound and the code quality is high, but it has never encountered the reality of satellite remote sensing data — different product layouts, non-overlapping spatial grids, atmospheric correction artifacts, and sensor-specific metadata paths.

---

## 1. Real Data Validation Report

### 1.1 Data Download (PASS)

`catalog.py` worked correctly:
- STAC catalog accessible at documented URL
- `list_fire_scenes()` returned 11 items (matching research documentation)
- `download_scene()` streaming download worked reliably
- Files landed correctly in `data/raw/fire/`

| Scene | Date | Phase | Size (MB) | Grid (rows×cols) | EPSG |
|-------|------|-------|-----------|------------------|------|
| `20241215_185916_33_4001` | 2024-12-15 | Pre-fire | 784.8 | 713×791 | 32611 |
| `20250123_185507_64_4001` | 2025-01-23 | Post-fire | 1319.4 | 1047×961 | 32611 |
| `20250407_192235_24_4001` | 2025-04-07 | Recovery | 1321.7 | 869×1039 | 32611 |

**Finding:** Ortho SR products are ~800-1300 MB each (not ~480 MB as estimated in engineering memory). The full 11-scene fire collection would be ~10-12 GB.

**Finding:** Surface reflectance IS available for all fire scenes via `ortho_sr_hdf5` product type. This resolves blocker B0 from research-memory.md.

### 1.2 Scene Loading (FAIL — P0)

`io.py` → `load_scene()` → `hypercoast.read_tanager()` **completely fails** on all three scenes:

```
ValueError: Could not locate Latitude/Longitude datasets in the Tanager HDF5 file.
```

**Root cause:** Ortho products use `HDFEOS/GRIDS/` (projected UTM grid) instead of `HDFEOS/SWATHS/` (with explicit lat/lon arrays). HyperCoast v0.22.0's `read_tanager()` hard-requires lat/lon datasets at line 422, which ortho grid products do not contain.

**Actual HDF5 structure (ortho SR):**
```
HDFEOS/GRIDS/HYP/Data Fields/
  surface_reflectance:              (426, 713, 791) float32
  surface_reflectance_uncertainty:  (426, 713, 791) float32
  beta_cirrus_mask:                 (713, 791) uint8
  beta_cloud_mask:                  (713, 791) uint8
  nodata_pixels:                    (713, 791) uint8
  aerosol_optical_depth:            (713, 791) float32
  column_water_vapour:              (713, 791) float32
  sensor_zenith/azimuth:            (713, 791) float32
  sun_zenith/azimuth:               (713, 791) float32
  time:                             (713, 791) float64
```

Grid coordinates come from StructMetadata.0: UTM Zone 11 (EPSG:32611), 30m pixel size.

**Workaround validated:** Direct h5py loading with xarray Dataset construction works perfectly. A custom `load_ortho_scene()` function is needed.

### 1.3 Bad Band Masking (PARTIAL PASS)

`spectral.py` → `mask_bad_bands()` correctly removes 98 of 426 bands, leaving 328 usable bands.

**Issue 1:** The sensor provides a `good_wavelengths` attribute on the surface_reflectance dataset that flags 58 bands as bad. Our `BAD_BAND_RANGES` are close but not identical:
- Sensor flags 1342-1432 nm → Pipeline removes 1340-1480 nm (wider — conservative, OK)
- Sensor flags 1782-1967 nm → Pipeline removes 1790-1960 nm (**narrower — misses bands 1782-1790 nm and 1960-1967 nm**)
- Pipeline removes <400 nm and >2350 nm (sensor doesn't flag these — pipeline is more conservative, which is appropriate)

**Recommendation:** Use `good_wavelengths` attribute from HDF5 as additional/primary mask source, OR widen `BAD_BAND_RANGES[2]` to `(1780, 1970)`.

### 1.4 Spectral Indices (FAIL — P1)

All four spectral indices produce **physically impossible values** on real data:

| Index | Expected Range | Actual Range (Pre-fire) | Actual Range (Post-fire) |
|-------|---------------|------------------------|-------------------------|
| NBR | [-1, 1] | **[-99.33, 0.86]** | [-0.93, 0.93] |
| NDVI | [-1, 1] | **[-1.53, 5.04]** | [-0.93, 3.77] |
| NDWI | [-1, 1] | **[-0.81, 1.17]** | [-0.92, 1.01] |

**Root cause:** Surface reflectance values contain:
- 13.2% negative values (atmospheric correction artifacts in shadow/dark pixels — normal for ISOFIT)
- 0.09% values > 1.0 (calibration artifacts)
- Extreme outliers: range [-37.6, 39.2] for pre-fire scene

When two bands near zero are used in a normalized difference, the denominator approaches zero while the numerator is non-zero, producing extreme ratios. The `_normalized_difference()` function only guards against `denominator == 0` (exact zero), not near-zero values.

**Synthetic tests pass** because test fixtures use clean reflectance in [0, 1] with no outliers.

### 1.5 Cloud Masking (FAIL — P1)

`masks.py` → `cloud_mask()` **fails to find beta_cirrus_mask** in ortho products:

```
WARNING: cloud_mask: beta_cirrus_mask not found in dataset or source HDF5.
Returning all-True mask (all pixels assumed cloud-free).
```

**Root cause:** `_read_beta_cirrus_from_hdf5()` searches these paths:
1. `/HDFEOS/SWATHS/HYP/Metadata/beta_cirrus_mask` — doesn't exist in ortho
2. `/HDFEOS/SWATHS/HYP/Data Fields/beta_cirrus_mask` — doesn't exist in ortho
3. `/Metadata/beta_cirrus_mask` — doesn't exist
4. `/beta_cirrus_mask` — doesn't exist

**Actual path:** `/HDFEOS/GRIDS/HYP/Data Fields/beta_cirrus_mask`

**Additional issue:** `beta_cloud_mask` also exists in the file but is completely ignored by the pipeline. Both masks should be combined for robust cloud detection.

### 1.6 dNBR / Multi-Temporal Analysis (FAIL — P1)

`spectral.py` → `dnbr()` **raises ValueError** because pre/post scenes have completely different spatial grids:

```
ValueError: Spatial dimensions of pre and post datasets must match:
pre is (713, 791), post is (1047, 961).
```

| Scene | Grid (y × x) | X Range (UTM m) | Y Range (UTM m) |
|-------|--------------|-----------------|-----------------|
| Pre-fire | 713 × 791 | 329,340 – 353,070 | 3,754,410 – 3,775,800 |
| Post-fire | 1047 × 961 | 345,105 – 373,905 | 3,805,935 – 3,837,315 |
| Recovery | 869 × 1039 | 341,310 – 372,480 | 3,818,850 – 3,844,920 |

**Critical observation:** The pre-fire and post-fire scenes have **minimal spatial overlap**. Their UTM grid extents barely intersect. The pre-fire scene covers the Malibu/Pacific Palisades coast area while the post-fire scene covers the Eaton Fire area further north/east.

**Implication:** dNBR between these specific scenes is scientifically questionable — they don't cover the same fire. The Jan 23 second swath (20250123_185518_92_4001) may overlap better with the Dec 15 pre-fire scene.

**Missing capability:** No spatial co-registration or reprojection function exists. The pipeline needs `rasterio.warp.reproject()` or equivalent to align scenes to a common grid before multi-temporal analysis.

### 1.7 Water Masking (MARGINAL)

`water_mask()` classified only 43% of valid pixels as land in the pre-fire scene. The pre-fire scene covers coastal LA including Pacific Ocean, so significant water is expected. However, the exact fraction depends on the NDWI threshold and the quality of the input reflectance.

NaN pixels (nodata) correctly propagate through NDWI to produce NaN, which the threshold comparison treats as "not land." When combined with `nodata_mask()` via `apply_masks()`, the behavior is correct.

### 1.8 Spatial Info (PASS)

`get_spatial_info()` correctly extracts CRS, bounds, resolution, and shape from the directly-loaded Dataset. CRS detection via `dataset.attrs["crs"]` works correctly.

---

## 2. Adversarial Review — Three Perspectives

### Perspective A — Remote Sensing Scientist

**Grade: FAIL — methodology is sound but implementation has critical gaps**

#### Finding A1 (P0): The spectral processing pipeline has never touched real satellite data

Every spectral operation was validated against synthetic fixtures with:
- Reflectance values cleanly in [0, 1]
- Perfect wavelength alignment to config values
- No atmospheric absorption artifacts
- No nodata pixels
- Matching spatial dimensions between scenes

Real Tanager data has: 13% negative reflectance (ISOFIT shadow artifacts), extreme outliers (reflectance = 39.2), non-uniform wavelength grids, 28% nodata fraction, and completely different spatial extents between acquisitions.

**Impact:** The tests validate formula correctness but not physical plausibility — the most important quality for a remote sensing pipeline.

#### Finding A2 (P1): Band selection uses hardcoded wavelengths from Landsat/Sentinel-2 heritage

`BAND_ALIASES` in config.py maps band names to wavelengths:
```python
BAND_ALIASES = {
    "BLUE": 470, "GREEN": 560, "RED": 660,
    "RED_EDGE": 705, "NIR": 860, "SWIR1": 1610, "SWIR2": 2200,
}
```

These are Landsat/Sentinel-2 center wavelengths, not Tanager-optimized selections. With 5nm spectral sampling, Tanager can resolve spectral features that broadband sensors cannot. For example:
- The 660nm "RED" band sits between two chlorophyll absorption features (645nm and 675nm)
- Tanager's 5nm sampling can target 675nm specifically for better vegetation discrimination
- The "NIR" at 860nm ignores the red-edge inflection point at ~720nm which is more sensitive to vegetation stress

This isn't a bug per se — the formulas are standard — but it represents a missed opportunity for spectral advantage that a competition judge would notice.

#### Finding A3 (P1): Continuum removal implementation has upper-hull extraction concerns

The `_continuum_removal_spectrum()` function uses `scipy.spatial.ConvexHull` and takes `hull.vertices` — which includes ALL convex hull boundary points (upper AND lower hull). For continuum removal, only the upper hull should be used. The implementation then interpolates all hull vertices, which may produce an incorrect continuum for spectra with strong absorption features where lower-hull points would pull the interpolated continuum below the actual upper envelope.

#### Finding A4 (P1): Reflectance data quality requires preprocessing before analysis

Surface reflectance from ISOFIT atmospheric correction produces:
- Negative values in shadow/dark pixels (13% of valid pixels)
- Values > 1.0 from calibration artifacts (0.09%)
- Fill value -9999 (correctly handled by masking)

These must be clamped or filtered before computing normalized-difference indices. Standard practice in the hyperspectral community is to: (1) clamp reflectance to [0, 1], or (2) apply a per-band SNR threshold and mask low-quality pixels.

#### Finding A5 (P2): FWHM is not constant — varies 5.20 to 6.81 nm across bands

Config.py states `spectral_resolution_nm=5` and research assumes FWHM=5.5nm. Actual per-band FWHM from HDF5 metadata varies from 5.20 to 6.81 nm. Phase 3 endmember resampling via SPy `BandResampler` must use the per-band FWHM array, not a constant.

#### Finding A6 (P2): Actual wavelength range differs from config

Config: `wavelength_min_nm=380, wavelength_max_nm=2500`
Actual: 376.44 – 2499.00 nm

Minor but scientifically sloppy in a competition submission.

### Perspective B — Data Engineer

**Grade: FAIL — pipeline is non-functional for the target product type**

#### Finding B1 (P0): io.py is broken for ortho products — the only product type the project intends to use

The engineering memory states "Use Ortho products only" and "Basic products are ungridded." But `load_scene()` wraps `hypercoast.read_tanager()` which only handles SWATHS-based products (basic). The entire I/O layer needs a custom ortho grid reader.

This isn't a minor edge case — it's the primary data path. Every downstream function depends on `load_scene()` producing an xarray Dataset, and that function fails on 100% of the intended input files.

#### Finding B2 (P0): Cloud mask searches wrong HDF5 paths for ortho products

`_read_beta_cirrus_from_hdf5()` only searches SWATHS-based paths. The actual path in ortho products is `HDFEOS/GRIDS/HYP/Data Fields/beta_cirrus_mask`. Fix: add GRIDS path to candidate list.

#### Finding B3 (P1): No spatial alignment capability — multi-temporal analysis impossible

The three scenes have different spatial extents AND the pre/post fire scenes barely overlap geographically. The pipeline needs:
1. A spatial co-registration function (rasterio.warp.reproject to common grid)
2. Logic to find the overlapping extent between scenes
3. Validation that scenes actually cover the same area before computing dNBR

#### Finding B4 (P1): No download integrity verification

Files are downloaded with streaming HTTP but no checksum verification. STAC metadata doesn't include file sizes (all return None). A corrupted download would silently produce garbage.

#### Finding B5 (P1): Scene geographic classification is wrong for 4 of 11 scenes

Based on STAC bounding boxes:

| Scene | Config Phase | Actual Location | Correct Phase |
|-------|-------------|-----------------|---------------|
| `20250724_190927_83_4001` | mid-recovery (LA) | **Utah** (38.5°N, -112°W) | other |
| `20250902_190116_02_4001` | late-recovery (LA) | **Utah** (38.5°N, -112°W) | other |
| `20250902_190121_86_4001` | late-recovery (LA) | **Utah** (38.5°N, -112°W) | other |
| `20250920_193207_61_4001` | other (N. Arizona) | **LA area** (33.9°N, -118.5°W) | late-recovery |

Three "LA fire recovery" scenes are actually in Utah. One "other" scene is actually in the LA area. The `FIRE_SCENES` dict in config.py has incorrect phase labels and `days_relative_to_ignition` values for these scenes.

#### Finding B6 (P2): `beta_cloud_mask` exists but is ignored

Ortho products contain both `beta_cirrus_mask` and `beta_cloud_mask`. Only cirrus is used. Both should be combined (`OR`) for complete cloud detection.

#### Finding B7 (P2): `nodata_pixels` HDF5 field is unused

The explicit `nodata_pixels` field (uint8, 0=valid, 1=nodata) provides direct nodata identification without needing to scan all 426 bands for NaN values. More efficient and reliable.

### Perspective C — Competition Judge

**Grade: AT RISK — strong methodology, weak execution, unfished pipeline**

#### Scoring Assessment

| Category | Points | Current State | Risk |
|----------|--------|---------------|------|
| Scientific Integrity & Innovation (30) | Strong methodology | Pipeline can't actually run on data | **HIGH** |
| Application or Use Case (30) | LA wildfire is compelling | Geographic errors undermine credibility | **MEDIUM** |
| Workflow & Tool Development (20) | Clean code, good tests | Tests don't use real data; I/O layer broken | **HIGH** |
| Visualization & Storytelling (20) | Not started | Phase 4 | DEFERRED |
| Tie-breaker: Tanager advantage (+5) | 426 bands at 5nm | Not yet demonstrated quantitatively | DEFERRED |
| Tie-breaker: Open source (+5) | MIT license, pip-installable | Broken pipeline hurts credibility | **HIGH** |

#### Strengths a judge would note:
1. **Novel LFMC contribution** — first satellite hyperspectral LFMC product
2. **Strong literature foundation** — 20+ papers cited, methodology well-justified
3. **Complete temporal coverage** — 7 dates spanning pre-fire through 6-month recovery
4. **Clean, well-documented code** — Google-style docstrings, type hints, structured tests

#### Weaknesses a judge would critique:
1. **The pipeline has never run on real data** — this would be immediately obvious to a technical reviewer
2. **159 tests but zero integration tests** — all mocked, no real-data fixtures
3. **Geographic errors in scene inventory** — labeling Utah scenes as "LA fire recovery" shows lack of data verification
4. **No visualization** — 20% of score, currently zero capability
5. **Over-reliance on HyperCoast** — a single library dependency that doesn't support the target product type

---

## 3. Bugs Found — Summary

| ID | Severity | Title | Module | Status |
|----|----------|-------|--------|--------|
| BUG-1 | **P0** | `load_scene()` fails on ortho SR products (HyperCoast lat/lon requirement) | io.py | Must fix |
| BUG-2 | **P0** | `cloud_mask()` searches wrong HDF5 paths for ortho products | masks.py | Must fix |
| BUG-3 | **P1** | Spectral indices produce impossible values (NBR=-99, NDVI=5) with real reflectance | spectral.py | Must fix |
| BUG-4 | **P1** | `dnbr()` fails — scenes have different spatial grids, no co-registration exists | spectral.py | Must fix |
| BUG-5 | **P1** | Scene geographic misclassification — 3 Utah scenes labeled as LA recovery | config.py | Must fix |
| BUG-6 | **P1** | BAD_BAND_RANGES misaligned with sensor `good_wavelengths` (misses 1782-1790nm) | config.py/spectral.py | Should fix |
| BUG-7 | **P1** | Pre/post fire scene swaths don't overlap — wrong scene pairing for dNBR | config.py | Must verify |
| BUG-8 | **P2** | `beta_cloud_mask` exists in HDF5 but is ignored by cloud_mask() | masks.py | Should fix |
| BUG-9 | **P2** | `nodata_pixels` HDF5 field unused (infers nodata from NaN scan instead) | masks.py | Should fix |
| BUG-10 | **P2** | FWHM varies 5.20-6.81nm, not constant 5.5nm as assumed | config.py | Fix for Phase 3 |
| BUG-11 | **P2** | Wavelength range 376.44-2499nm, not 380-2500nm as in config | config.py | Should fix |
| BUG-12 | **P2** | Continuum removal uses full convex hull, not upper hull only | spectral.py | Should fix |
| BUG-13 | **P2** | No download integrity verification (no checksums) | catalog.py | Low priority |

---

## 4. Verdict

### **NOT DEFENSIBLE**

The pipeline cannot load, process, or analyze real Tanager satellite data in its current state. The 4 blocking issues (P0 + critical P1s) must be resolved before Phase 3 can begin:

1. **io.py must support ortho grid products** — either fix HyperCoast upstream or implement a direct h5py reader (the direct reader was validated in this review and works correctly)
2. **cloud_mask must search GRIDS paths** — simple fix, add `/HDFEOS/GRIDS/HYP/Data Fields/beta_cirrus_mask` to candidate paths
3. **Spectral indices must handle real reflectance** — clamp reflectance to [0, 1] before computing normalized differences, or guard against near-zero denominators
4. **Spatial alignment capability is required** — dNBR and multi-temporal analysis are core to FireSpec; they require co-registered scenes

### Recommended Remediation Path

1. **Immediate (before Phase 3):**
   - Implement `load_ortho_scene()` in io.py using direct h5py reader
   - Fix cloud_mask HDF5 path candidates for ortho products
   - Add reflectance clamping or near-zero denominator guard to `_normalized_difference()`
   - Fix scene geographic classifications in config.py
   - Add `good_wavelengths` sensor mask integration to `mask_bad_bands()`

2. **Before dNBR / multi-temporal work:**
   - Implement spatial alignment function (rasterio reproject to common grid)
   - Verify which scene pairs actually overlap for valid dNBR computation
   - Consider downloading additional scenes to find proper pre/post overlap

3. **Before submission:**
   - Add real-data integration tests (at minimum: load a real scene, compute indices, verify ranges)
   - Fix continuum removal upper-hull extraction
   - Update metadata (wavelength range, FWHM) in config.py

---

## Appendix: Data Validation Details

### Scene Reflectance Statistics (valid pixels only, fill=-9999 masked)

| Metric | Pre-fire (Dec 15) | Post-fire (Jan 23) | Recovery (Apr 7) |
|--------|-------------------|-------------------|-----------------|
| Valid fraction | 71.4% | 69.3% | 76.4% |
| Min reflectance | -37.61 | -0.55 | -0.47 |
| Max reflectance | 39.17 | 17.38 | 6.79 |
| Mean reflectance | 0.051 | — | — |
| Negative fraction | 13.2% | 10.3% | — |
| Values > 1.0 | 0.09% | — | — |

### Wavelength Grid (from HDF5 metadata)

- Range: 376.44 – 2499.00 nm
- Bands: 426 contiguous
- Spacing: 4.95 – 5.02 nm (mean 4.99 nm)
- FWHM: 5.20 – 6.81 nm (not constant)
- Sensor-flagged bad bands: 58 (1342-1432 nm, 1782-1967 nm)
- Pipeline-masked bad bands: 98 (<400, 1340-1480, 1790-1960, 2350-2500 nm)
- Usable bands after masking: 328

### Cloud/Quality Mask Statistics

| Mask | Pre-fire | Recovery |
|------|----------|----------|
| beta_cirrus_mask (cloudy) | 0.00% | 0.00% |
| beta_cloud_mask (cloudy) | present | 0.11% |
| nodata_pixels (nodata) | 28.6% | — |
