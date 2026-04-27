# Research Memory: Tanager Competition

> Long-term memory for research agents. Tracks literature, experiments, data sources, and scientific findings.

**Location:** `/docs/research-memory.md`
**Owner:** Tobler (Research Lead)
**Updated:** 2026-04-27
**Version:** 2.0

---

## Purpose

This is the third tier of the memory system, specific to research-heavy projects. It tracks:
1. **Literature** — Key papers, their findings, and relevance
2. **Data sources** — Datasets, spectral libraries, reference data
3. **Experiments** — What was tried, what worked, what didn't
4. **Scientific context** — Domain knowledge critical for the project

---

## Tanager-1 Sensor Characterization

| Parameter | Value |
|-----------|-------|
| Bands | 426 (contiguous VSWIR) |
| Spectral range | 380–2500 nm |
| Spectral resolution | ~5 nm spacing |
| First band | 376.44 nm |
| FWHM | ~5.4 nm (varies slightly across range) |
| GSD | 30 m (observed: 32.58–39.12 m) |
| Swath width | 18 km |
| Scene size | 325–750 lines × ~600 cols |
| Detector | 640×480 MCT focal plane array |
| SNR | 300–600 (mode dependent) |
| Data format | HDF-EOS5 (.h5) |
| Atmospheric correction | ISOFIT v2.9.5 (for SR products) |
| Operator | Planet Labs PBC |
| Launch | August 16, 2024 |
| Satellite ID | 4001 |

---

## Available Data

### STAC Catalog Access

- **Catalog URL:** `https://www.planet.com/data/stac/tanager-core-imagery/catalog.json`
- **Type:** Static STAC catalog (NOT a STAC API)
- **Auth:** None required (CC BY 4.0)
- **Python:** Use `pystac` (NOT `pystac-client`)
- **Total scenes:** 150+ across 9 collections

### LA Wildfire Fire Collection (12 scenes)

| Date | Scene ID | Phase | Days Since Ignition |
|------|----------|-------|---------------------|
| 2024-12-15 | 20241215_185916_33_4001 | **Pre-fire baseline** | -23 |
| 2025-01-23 | 20250123_185507_64_4001 | **Immediate post-fire** | +16 |
| 2025-01-23 | 20250123_185518_92_4001 | Post-fire (adjacent swath) | +16 |
| 2025-04-07 | 20250407_192235_24_4001 | **Early recovery** | +90 |
| 2025-04-07 | 20250407_192229_16_4001 | Early recovery (adjacent) | +90 |
| 2025-07-24 | 20250724_190927_83_4001 | **Mid recovery** | ~200 |
| 2025-07-26 | 20250726_192343_21_4001 | Mid recovery | ~200 |
| 2025-07-26 | 20250726_192422_87_4001 | Mid recovery (adjacent) | ~200 |
| 2025-09-02 | 20250902_190116_02_4001 | **Late recovery** | ~240 |
| 2025-09-02 | 20250902_190121_86_4001 | Late recovery (adjacent) | ~240 |
| 2025-09-20 | 20250920_193207_61_4001 | Likely Northern Arizona | N/A |

- **Coverage:** LA area (Palisades 23,448 ac + Eaton 14,021 ac, ignited Jan 7 2025) + Northern Arizona
- **Spatial extent:** lon -118.91 to -111.82, lat 33.90 to 38.76
- **Product types:** Basic Radiance, Ortho Radiance, Basic SR, Ortho SR (4 per scene)
- **Primary product:** Ortho Surface Reflectance (~480 MB/scene, ~6 GB total for fire collection)
- **Status:** Not yet downloaded

### Other Available Collections
- Agriculture (~43 scenes): Germany (10), Kenya (8), California, India, etc.
- Natural Lands (~77 scenes): Global
- Urban (~60 scenes): LA, Buenos Aires, Netherlands, etc.
- Coastal & Water Bodies: San Francisco Bay featured
- GHG Plumes: Turkmenistan, Texas, Algeria, South Africa
- Snow & Ice, Energy & Mining, ROCX 2025

---

## Key Literature

### Hyperspectral Wildfire Analysis
| Paper/Source | Key Finding | Relevance |
|-------------|-------------|-----------|
| Veraverbeke et al. (2018) RSE 216 | Comprehensive review: hyperspectral enables fuel mapping, severity, emissions, recovery impossible with multispectral | Foundational framework for FireSpec scope |
| Veraverbeke et al. (2014) RSE 154 | AVIRIS burned fraction vs GeoCBI R²=0.86, significantly better than Landsat | Upper bound for severity accuracy from imaging spectroscopy |
| Quintano et al. (2023) RSE 113670 | PRISMA MESMA R²=0.64-0.79 vs Sentinel-2 R²=0.27-0.53 for CBI | Direct methodological template; proves spaceborne viability |
| Robichaud et al. (2007) RSE | MTMF on AVIRIS for post-Hayman Fire ash/soil/vegetation fractions | Early validation of hyperspectral unmixing for post-fire soil |

### Spectral Unmixing (MESMA)
| Paper/Source | Key Finding | Relevance |
|-------------|-------------|-----------|
| Quintano et al. (2013) RSE | MESMA on Landsat with Char/GV/NPVS/Shade; kappa>0.75 | Established MESMA for fire; endmember framework we adopt |
| Tane et al. (2018) Remote Sensing 10(3) | Evaluated IES, In-CoB, EAR, MASA for post-fire MESMA | Best practices for endmember selection |
| Fernandez-Manso et al. (2016) RSE 184 | Multi-temporal Landsat MESMA fraction time series for recovery | Validates temporal trajectory approach for LA time series |
| Dennison & Roberts (2003) RSE 41 | Foundational EAR/MASA metrics for chaparral MESMA | Core algorithms for endmember library construction |

### Live Fuel Moisture Content (LFMC)
| Paper/Source | Key Finding | Relevance |
|-------------|-------------|-----------|
| Yebra et al. (2013) RSE review | Global review; water bands at 970, 1200, 1450, 1940nm | Definitive review; key wavelengths and accuracy requirements |
| Qi et al. (2014) RSE 150 | PLSR R²=0.72-0.94 leaf level; dry mass confounds water signal | PLSR methodology + cautionary wavelength interpretation |
| Riano et al. (2005) IEEE TGRS 43 | PROSPECT inversion for EWT+DM; water masks DM in fresh leaves | RTM approach reference |
| Danson & Bowyer (2004) RSE | GA-PLS R²=0.82-0.89; bands at 1144, 1304, 1670, 1750nm | Optimal SWIR wavelengths for LFMC |
| Marino et al. (2022) Remote Sensing 14(13) | RF+MODIS LFMC RMSE=16-20% at landscape scale | Baseline to beat with Tanager hyperspectral |

---

## Spectral Libraries & Reference Data

| Resource | URL | Purpose |
|----------|-----|---------|
| USGS Spectral Library v7 | usgs.gov/labs/spectroscopy-lab | Endmember spectra for unmixing |
| ECOSTRESS Spectral Library | speclib.jpl.nasa.gov | Additional vegetation spectra |
| (More TBD) | | |

---

## Tools Evaluated

| Tool | Purpose | Verdict | Notes |
|------|---------|---------|-------|
| HyperCoast | Tanager data I/O + viz | **USE** | `read_tanager()` → xarray Dataset, handles all 4 product types |
| pystac | STAC catalog browsing | **USE** | Static catalog reader; pystac-client will NOT work |
| spectral (SPy) | Spectral analysis | **USE** | MESMA, SAM; needs numpy from xarray |
| mesma (Python) | MESMA unmixing | **EVALUATE** | v1.0.8, dedicated MESMA package |
| scikit-learn | PLSR, Random Forest | **USE** | PLSRegression for LFMC, RFR for CBI |
| spyndex | Spectral indices | **USE** | Works with any array data |
| earthaccess | NASA data access | **NOT APPLICABLE** | For EMIT/PACE only, not Tanager |
| pysptools | Spectral unmixing | **EVALUATE** | Alternative MESMA implementation |

---

## Experiments Log

| Date | Experiment | Result | Notes |
|------|-----------|--------|-------|
| (TBD — Phase 2) | | | |

---

## Open Questions

### Answered
1. ~~What atmospheric correction is needed?~~ → Planet provides L2 SR via ISOFIT v2.9.5. No additional correction needed.
4. ~~How does Tanager's 30m GSD compare to airborne?~~ → Same GSD as PRISMA/EnMAP; R²=0.79 achieved at 30m (Quintano 2023).

### Open
2. Which endmember spectra best represent LA fire-affected vegetation?
3. What is the optimal band subset for LFMC estimation? (Literature suggests 970, 1200, 1680, 2100, 2280nm)
5. Can we validate against BARC maps for the LA fires?
6. Best MESMA software for Python — mesma v1.0.8, SPy, or pysptools?
7. Can we obtain field CBI measurements for the LA fires?
8. Exact STAC asset keys — need to inspect item.json to confirm naming
9. Do all 12 fire scenes have SR products, or only radiance?
10. Spatial overlap between Dec 15 pre-fire and Jan 23 post-fire scenes?
11. EMIT scenes over same LA area for cross-sensor validation?
