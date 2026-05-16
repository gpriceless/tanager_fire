# Sensor Comparison Research: Tanager vs EMIT/PRISMA/Sentinel-2

**Author:** Tobler (Geospatial Data Scientist)
**Date:** 2026-05-04
**Competition tie-breaker:** +5 points for quantitative Tanager vs EMIT/PRISMA comparison
**Paperclip issue:** LGT-398

---

## Executive Summary

The Tanager competition awards +5 tie-breaker points for a quantitative sensor comparison. This report assesses data availability for three comparison sensors (EMIT, PRISMA, Sentinel-2) over the LA fires (Jan 2025) and recommends a dual-track methodology: (1) spectral degradation simulation as the primary approach (clean, controls confounds) and (2) real Sentinel-2 dNBR as a broadband baseline.

**Key findings:**
- **PRISMA:** Confirmed post-fire scene Jan 12, 2025. Free for research, registration required. No published PRISMA analysis of LA fires — open field.
- **EMIT:** ISS orbit makes coverage uncertain. Data availability requires Earthdata search.
- **Sentinel-2:** ~5-day revisit guaranteed. Multiple cloud-free scenes expected. dNBR methodology well-established.
- **Spectral degradation simulation** is the strongest methodology — same scene, same atmosphere, isolates spectral resolution advantage.

---

## 1. Sensor Specifications

| Parameter | Tanager-1 | EMIT | PRISMA | Sentinel-2 |
|-----------|-----------|------|--------|------------|
| Bands | 426 | 285 | 239 | 13 |
| Spectral range | 380–2500 nm | 381–2493 nm | 400–2505 nm | 443–2190 nm |
| Spectral sampling | ~5 nm | ~7.4 nm | ~12 nm | 15–180 nm |
| FWHM | 5.2–6.8 nm | ~8.5 nm | <12 nm | 15–180 nm |
| GSD | 30 m | 60 m | 30 m | 10–60 m |
| Orbit | Sun-sync (406 km) | ISS (~52° incl.) | Sun-sync (615 km) | Sun-sync (786 km) |
| Revisit | On-demand | Variable (ISS) | ~16 days | ~5 days (2A+2B) |
| Status | Operational | Operational | Extended (EOL Dec 2026) | Operational |
| Data access | CC BY 4.0 (open) | NASA Earthdata (free) | ASI portal (free, registration) | Copernicus (free) |

**Tanager advantage:** Finest spectral sampling (5 nm) of any spaceborne imaging spectrometer. 1.5× more bands than EMIT, 1.8× more than PRISMA, 33× more than Sentinel-2.

---

## 2. Data Availability Assessment

### 2.1 PRISMA

**Status: CONFIRMED — post-fire scene available**

- **Confirmed scene:** Jan 12, 2025 (5 days post-fire) over Palisades fire area
- **Source:** ASI official news post showing false-color composite of burn area
- **Access:** Free for non-commercial/research use; register at https://prismauserregistration.asi.it/
- **Products:** L2D (orthorectified surface reflectance) or NASA SISTER L2A via ORNL DAAC
- **Format:** HDF5
- **Pre-fire:** Uncertain — depends on whether tasking requests were submitted for LA in late 2024. 16-day revisit means coverage not guaranteed. Must search ASI catalog.
- **Redistribution:** Cannot redistribute raw PRISMA data, but derived products are fine for competition.
- **Published analyses:** None for LA 2025 fires — this would be novel.

**Action:** Register for ASI portal, search for LA-area scenes Dec 2024 – Jul 2025.

### 2.2 EMIT

**Status: PLAUSIBLE — extended mission expanded coverage beyond arid regions**

- EMIT entered extended mission in early 2024, expanding beyond arid dust source regions to include agriculture, hydrology, snowpack, and other land cover types
- ISS orbit (51.6° inclination, 407 km) covers LA latitude (~34°N) but revisit is irregular (not systematic)
- Average 3 visits per target region; LA may have 0–3 scenes in a 7-month window
- Data is free via NASA Earthdata / LP DAAC; `earthaccess` Python library handles auth + S3 streaming
- Products: L1B (TOA radiance), L2A (surface reflectance — primary interest), L2B (minerals, methane)
- **AVIRIS-3 airborne data already exists** for LA fires (Jan 10 and 16, 2025, 3–4m resolution) — serves as spectral ground truth
- No published EMIT analysis of the 2025 LA fires found — novelty opportunity if data exists
- EMIT and Tanager share JPL design heritage; spectral ranges nearly identical (381–2493nm vs 380–2500nm)

**Action:** Query CMR API for EMITL2ARFL granules over LA bounding box (33.8–34.3°N, 118.0–118.8°W), Dec 2024 – Jul 2025. Human may need to run:
```python
import earthaccess
earthaccess.login()
results = earthaccess.search_data(
    short_name="EMITL2ARFL",
    bounding_box=(-118.8, 33.8, -118.0, 34.3),
    temporal=("2024-12-01", "2025-07-31")
)
print(f"Found {len(results)} EMIT L2A granules over LA")
```

### 2.3 Sentinel-2

**Status: CONFIRMED — extensive coverage with published analyses**

- **Revisit:** 2–5 day cadence (2B+2C in late 2024; 2A rejoined March 2025 for 2–3 day cadence)
- **Estimated cloud-free scenes:** 15–20 in Dec 2024 – Jul 2025 (LA winter ~31% cloud cover, summer <10%)
- **Primary tile:** T11SLT (covers Palisades/Santa Monica Mountains area)
- **Copernicus EMS EMSR746 activated** for LA fires — grading products with burn severity maps downloadable
- **Published analyses exist:**
  - ResearchGate: Sentinel-2 dNBR with pre-fire Aug 26, 2024 and post-fire Jan 12, 2025; mapped 17,043 ha burned
  - arXiv (2501.17880v1): Multi-modal Sentinel-2 analysis; shrubland 57–76% of burned areas
  - ScienceDirect: Multi-sensor approach (S2 + SAR) for Palisades fire
- **MTBS** will produce official 30m burn severity GeoTIFFs for Palisades (10,961 ha) and Eaton (5,326 ha)
- **NASA HLS** combines Landsat 8/9 + Sentinel-2 at 30m for ~1.4-day average revisit

**Key bands for fire:**
| Band | Center (nm) | Bandwidth (nm) | GSD (m) | Use |
|------|-------------|----------------|---------|-----|
| B4 (Red) | 665 | 30 | 10 | NDVI |
| B8A (Narrow NIR) | 865 | 20 | 20 | NBR numerator |
| B11 (SWIR-1) | 1610 | 90 | 20 | NDWI |
| B12 (SWIR-2) | 2190 | 180 | 20 | NBR denominator |

**NBR formula:** (B8A – B12) / (B8A + B12)

**Action items:**
1. Download EMSR746 grading products from rapidmapping.emergency.copernicus.eu/EMSR746/
2. Download Sentinel-2 L2A pre-fire (~Dec 28 or Jan 2) and post-fire (Jan 12) from Copernicus Data Space
3. Check MTBS direct download (mtbs.gov/direct-download) for official severity products
4. Download LA County fire perimeters from egis-lacounty.hub.arcgis.com

---

## 3. Recommended Comparison Methodology

### 3.1 Primary: Spectral Degradation Simulation (Approach B)

**Rationale:** Using the same Tanager scene convolved to different spectral resolutions isolates the spectral resolution advantage from confounds (different acquisition dates, atmospheric conditions, viewing geometry, spatial resolution).

**Method:**
1. Start with a Tanager 426-band scene (e.g., 20241215 pre-fire or 20250123 post-fire)
2. Use SPy `BandResampler` to convolve Tanager spectra to:
   - **Simulated EMIT:** 285 bands, 381–2493 nm, 7.4 nm sampling, 8.5 nm FWHM
   - **Simulated PRISMA:** 239 bands, 400–2505 nm, ~12 nm sampling, 12 nm FWHM
   - **Simulated Sentinel-2:** 13 bands at discrete center wavelengths with specified bandwidths
3. Run the same fire metrics on native and simulated data:
   - NBR/dNBR
   - MESMA unmixing (char/PV/NPV/soil fractions)
   - LFMC indices (SAI970, SAI1200, NDWI variants, CR depths)
4. Compare results using `validation.compare_sensors()`:
   - Continuous: R², RMSE, MAE vs ground truth (AVIRIS-3, BARC)
   - Classified: Accuracy, Kappa, F1 vs BARC severity classes
5. Generate improvement ratio tables and visualizations

**Strengths:**
- Controlled experiment — only spectral resolution varies
- Same spatial resolution, same atmosphere, same scene
- Publishable methodology (spectral degradation is well-established)
- No external data download required beyond what we already have
- Can run on any Tanager scene

**Expected results (based on Quintano et al. 2023 benchmarks):**
- Tanager vs S2: MESMA R² improvement of ~0.2–0.5 (S2 R²=0.27–0.53 vs hyperspectral R²=0.64–0.79)
- Tanager vs PRISMA: modest improvement (PRISMA already has 239 bands)
- Tanager vs EMIT: modest improvement + spatial resolution advantage (30m vs 60m)
- LFMC indices: Tanager's 5 nm sampling resolves narrow water absorption features that degrade at 12+ nm

### 3.2 Supplementary: Real Sentinel-2 dNBR Baseline (Approach A, partial)

**Method:**
1. Download Sentinel-2 pre-fire (Dec 2024) and post-fire (Jan 2025) L2A tiles
2. Compute S2 dNBR at 20 m resolution
3. Resample S2 dNBR to 30 m to match Tanager grid
4. Compare both against BARC reference severity map
5. Show Tanager hyperspectral MESMA/CBI outperforms S2 broadband dNBR

**Strengths:**
- Uses real sensor data (not simulated)
- Sentinel-2 is the standard baseline in fire RS
- Accounts for real-world differences (different acquisition times, atmospheric conditions)

**Limitations:**
- Different acquisition dates add confounds (vegetation phenology, weather)
- S2 at 20 m vs Tanager at 30 m — spatial resolution favors S2

### 3.3 Optional: Real PRISMA Comparison (if data is obtainable)

If the Jan 12 PRISMA scene is obtained:
1. Load PRISMA L2D (or SISTER L2A) surface reflectance
2. Co-register to Tanager grid (both 30 m)
3. Run MESMA on both Tanager and PRISMA data
4. Compare fractions against AVIRIS-3 reference
5. This would be the **first intercomparison of two spaceborne imaging spectrometers for wildfire**

---

## 4. Quantifying the Tanager Advantage

### 4.1 Spectral Resolution

| Feature | Tanager (5 nm) | Simulated EMIT (7.4 nm) | Simulated PRISMA (12 nm) | Simulated S2 |
|---------|----------------|-------------------------|--------------------------|--------------|
| Red edge (700–750 nm) | 10 bands | 7 bands | 4 bands | 2 bands (B5, B6) |
| NIR plateau (810–900 nm) | 18 bands | 12 bands | 8 bands | 2 bands (B8, B8A) |
| Water 970 nm feature | 6+ bands | 4 bands | 2 bands | 0 bands |
| Water 1200 nm feature | 8+ bands | 5 bands | 3 bands | 0 bands |
| SWIR char/ash (2000–2300 nm) | 60 bands | 40 bands | 25 bands | 1 band (B12) |

**Key advantage:** Tanager's 5 nm sampling resolves the 970 nm and 1200 nm water absorption features critical for LFMC estimation. These features are degraded at PRISMA's 12 nm and completely invisible to Sentinel-2's broadband filters.

### 4.2 Expected Performance Improvements

Based on Quintano et al. (2023) and Roberts et al. (2006):

| Metric | S2 Expected | PRISMA Expected | EMIT Expected | Tanager Expected |
|--------|-------------|-----------------|---------------|------------------|
| MESMA CBI R² | 0.27–0.53 | 0.64–0.79 | ~0.60–0.75 | 0.70–0.85 |
| LFMC R² | 0.55–0.65 | 0.65–0.75 | ~0.65–0.75 | 0.70–0.85 |
| dNBR accuracy | Baseline | +15–30% | +10–25% | +20–40% |

---

## 5. Implementation Spec

### 5.1 New Code: `config.py` additions

Add comparison sensor specifications:

```python
EMIT_SENSOR = SimpleNamespace(
    name="EMIT",
    n_bands=285,
    wavelength_min_nm=381,
    wavelength_max_nm=2493,
    spectral_resolution_nm=7.4,
    fwhm_nm=8.5,
    spatial_resolution_m=60,
)

PRISMA_SENSOR = SimpleNamespace(
    name="PRISMA",
    n_bands=239,
    wavelength_min_nm=400,
    wavelength_max_nm=2505,
    spectral_resolution_nm=12,
    fwhm_nm=12,
    spatial_resolution_m=30,
)

SENTINEL2_BANDS = {
    "B2": {"center_nm": 490, "fwhm_nm": 65, "gsd_m": 10},
    "B3": {"center_nm": 560, "fwhm_nm": 35, "gsd_m": 10},
    "B4": {"center_nm": 665, "fwhm_nm": 30, "gsd_m": 10},
    "B5": {"center_nm": 705, "fwhm_nm": 15, "gsd_m": 20},
    "B6": {"center_nm": 740, "fwhm_nm": 15, "gsd_m": 20},
    "B7": {"center_nm": 783, "fwhm_nm": 20, "gsd_m": 20},
    "B8": {"center_nm": 842, "fwhm_nm": 115, "gsd_m": 10},
    "B8A": {"center_nm": 865, "fwhm_nm": 20, "gsd_m": 20},
    "B11": {"center_nm": 1610, "fwhm_nm": 90, "gsd_m": 20},
    "B12": {"center_nm": 2190, "fwhm_nm": 180, "gsd_m": 20},
}
```

### 5.2 New Function: `validation.simulate_sensor()`

```python
def simulate_sensor(
    scene: xr.DataArray,
    target_centers: np.ndarray,
    target_fwhm: Union[float, np.ndarray],
    sensor_name: str,
) -> xr.DataArray:
    """Convolve Tanager 426-band data to simulate another sensor's bandpass.

    Uses SPy BandResampler for Gaussian-convolution-based spectral resampling.
    Input must have a 'wavelength' coordinate in nm with Tanager band centers.

    For Sentinel-2: pass the discrete band centers and broadband FWHM values.
    For EMIT/PRISMA: pass uniformly spaced centers with scalar FWHM.

    Returns DataArray with simulated sensor band centers as wavelength coordinate.
    """
```

### 5.3 New Pipeline Stage: `stage_sensor_comparison()`

```python
@_stage("sensor_comparison")
def stage_sensor_comparison(scene, scene_id, out_dir):
    """Run fire metrics at simulated EMIT/PRISMA/S2 spectral resolutions.

    For each simulated sensor:
    1. Convolve Tanager scene to target bandpass
    2. Compute NBR (and dNBR if pre/post pair available)
    3. Compute MESMA fractions (if endmember library available at target resolution)
    4. Compare accuracy against native Tanager results
    5. Generate improvement ratio tables
    """
```

### 5.4 New Loader (optional): `validation.load_sentinel2_dnbr()`

```python
def load_sentinel2_dnbr(
    filepath: FilePath,
    target_grid: Optional[xr.DataArray] = None,
) -> xr.DataArray:
    """Load a Sentinel-2 dNBR GeoTIFF and reproject to Tanager grid."""
```

### 5.5 Effort Estimate

| Component | Effort | Dependencies |
|-----------|--------|-------------|
| Config sensor specs | 30 min | None |
| `simulate_sensor()` function | 2 hrs | SPy BandResampler (already used) |
| Pipeline comparison stage | 3 hrs | simulate_sensor, existing metrics |
| Sentinel-2 data download + loader | 2 hrs | rasterio (already used) |
| PRISMA loader (optional) | 2 hrs | h5py (already used) |
| Comparison visualizations | 2 hrs | matplotlib (already used) |
| Tests | 2 hrs | Existing test patterns |
| **Total** | **~13 hrs** | No new dependencies |

---

## 6. Recommendations

### R1: Implement spectral degradation as Phase 4 work

The simulation approach requires no external data and uses existing infrastructure (SPy BandResampler). This should be part of the Phase 4 OpenSpec (which PQ is expected to spec).

### R2: Download Sentinel-2 pre/post-fire scenes now

Sentinel-2 data is freely available, no registration needed. Download tiles T11SLT/T11SMT for Dec 2024 and Jan 2025. Use as broadband baseline.

### R3: Register for PRISMA data access

Human effort required — register at ASI portal, search catalog for LA-area scenes. If the Jan 12, 2025 scene is obtainable, this enables a novel spaceborne hyperspectral intercomparison.

### R4: Search NASA Earthdata for EMIT scenes

Check LP DAAC for EMIT L2A scenes at 34°N, 118.3°W. If EMIT covered the LA fires, include in the comparison. If not, document the ISS orbit limitation as a sensor accessibility finding.

### R5: Position spectral degradation as the scientific contribution

The competition judges want "genuine scientific value, not just a checkbox exercise." A controlled spectral degradation experiment that quantifies how burn severity and LFMC accuracy degrade as spectral resolution decreases from 5 nm → 7.4 nm → 12 nm → broadband is a publishable result. Frame it as: "What spectral resolution does wildfire monitoring require?"

---

## Sources

- ASI: PRISMA observation of California wildfire (confirmed Jan 12, 2025 scene)
- Quintano et al. 2023 (DOI: 10.1016/j.rse.2023.113670) — PRISMA fire severity benchmark
- Roberts et al. 2006 (DOI: 10.1029/2005JG000113) — AVIRIS LFMC methodology
- Veraverbeke et al. 2018 (DOI: 10.1016/j.rse.2018.06.020) — Hyperspectral fire RS review
- Quan et al. 2021 (DOI: 10.1371/journal.pone.0249351) — SAI spectral indices for LFMC
