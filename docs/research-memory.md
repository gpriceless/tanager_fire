# Research Memory: Tanager Competition

> Long-term memory for research agents. Tracks literature, experiments, data sources, and scientific findings.

**Location:** `/docs/research-memory.md`
**Owner:** Tobler (Research Lead)
**Updated:** 2026-04-27
**Version:** 1.0

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
| Bands | 426 (contiguous) |
| Spectral range | VNIR + SWIR (~400-2500 nm) |
| GSD | 30 meters |
| Swath width | ~30 km |
| Operator | Planet Labs |
| Launch | 2024 |

---

## Available Data

### LA Wildfire Time Series
- **Scenes:** 7 acquisitions (Dec 2024 – Jul 2025)
- **Coverage:** Los Angeles region
- **Significance:** Pre-fire, active fire period, and post-fire recovery
- **Status:** Not yet downloaded — access via Planet API

### Other Available Scenes (from Tobler's research)
- Germany agricultural area (10 scenes)
- Kenya (8 scenes)
- Hawaii coral reef area

---

## Key Literature (To Be Populated)

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
| HyperCoast | Tanager data I/O | **USE** | Has `read_tanager()`, maintained by opengeos |
| spectral (SPy) | Spectral analysis | **USE** | MESMA, SAM, mature library |
| EMIT tools | Hyperspectral processing | **EVALUATE** | NASA's EMIT mission tools, may be adaptable |
| pysptools | Spectral unmixing | **EVALUATE** | Alternative MESMA implementation |

---

## Experiments Log

| Date | Experiment | Result | Notes |
|------|-----------|--------|-------|
| (TBD — Phase 2) | | | |

---

## Open Questions

1. What atmospheric correction is needed for Tanager data? (Planet may provide L2 products)
2. Which endmember spectra best represent LA fire-affected vegetation?
3. What is the optimal band subset for LFMC estimation?
4. How does Tanager's 30m GSD compare to airborne hyperspectral for burn severity?
5. Can we validate against BARC (Burned Area Reflectance Classification) maps?
6. What is the best MESMA software for Python — mesma package v1.0.8 or SPy's implementation?
7. Can we obtain field CBI measurements for the LA fires for validation?
