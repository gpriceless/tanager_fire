# Change: Core Analysis — MESMA Spectral Unmixing & LFMC Estimation

**Change ID:** 003-core-analysis
**Plane Issue:** TANAGER-10
**Status:** Approved (EM-enriched, ready for /run-phase)
**Author:** Product Queen
**Date:** 2026-04-27

---

## Why

Phase 2 delivered a robust data pipeline (catalog, I/O, spectral preprocessing, masking) — but the
project has zero analysis capability. The competition deadline is August 31, 2026. We need the two
analysis pillars that form FireSpec's core value proposition: (1) MESMA-based burn severity mapping
that outperforms broadband dNBR by ~2x (demonstrated in Quintano et al. 2023), and (2) live fuel
moisture content estimation — a product that does **not yet exist** from any spaceborne
hyperspectral sensor, giving us first-mover novelty for the competition.

Without this phase we have a data loader, not a submission.

## What Changes

### Track A: Endmember Library & Selection

- `src/tanager/endmembers.py` — **NEW** module for spectral library management
  - Load and resample endmember libraries (USGS v7, ECOSTRESS, FRAMES SoCal chaparral)
  - SPy `BandResampler` with Gaussian FWHM convolution (1nm source → 5nm Tanager band centers)
  - In-CoB (count-based) endmember selection within each class
  - EAR/MASA joint pruning via `spectral-libraries` v1.1.3 `EarMasaCob` class
  - Image-derived endmember extraction from Tanager scenes (PPI or spatial selection)
  - Library I/O: load from ASCII, SQLite (ECOSTRESS via SPy), SPECPR (USGS v7 via splib07-loader)
  - Target library size: ~52-78 spectra (Char 10-15, Ash 3-5, PV 20-30, NPV 10-15, Soil 8-12, Shade 1)

### Track B: MESMA Spectral Unmixing

- `src/tanager/unmixing.py` — **NEW** module for spectral mixture analysis
  - Wrapper around `mesma` v1.0.8 (primary) with HySUPP fallback
  - uSZU band selection from full spectrum → ~30-50 diagnostic bands
  - MESMA execution: pixel-by-pixel multi-endmember unmixing
  - Fraction map outputs: char, PV, NPV, soil, shade per pixel
  - RMSE constraint filtering (reject poor-fit pixels)
  - Shade normalization of fractions
  - Fraction map visualization utilities

### Track C: Burn Severity Mapping

- `src/tanager/severity.py` — **NEW** module for burn severity products
  - MESMA fractions → CBI-equivalent severity regression (Random Forest, scikit-learn)
  - Multi-temporal fraction trajectories (Dec 2024 → Jul 2025, 5 dates)
  - dNBR baseline comparison (uses existing `spectral.dnbr()`)
  - Severity classification: Unburned / Low / Moderate-Low / Moderate-High / High
  - Validation framework: compare against AVIRIS-3 Eaton Fire fractions + USGS BARC maps
  - Accuracy metrics: R², RMSE, bias, confusion matrix (for classified severity)

### Track D: LFMC Estimation

- `src/tanager/lfmc.py` — **NEW** module for live fuel moisture content
  - Tier 1: Spectral water absorption indices
    - SAI970, SAI1200, SAI1660 (spectral absorption index at 970, 1200, 1660 nm)
    - NDWI variants: NDWI(860,1240), NDWI(860,1640), NDWI(860,2130)
    - Water Index: R900/R970
    - Continuum removal band depths at 970, 1200, 1700, 2100 nm (leverages existing `continuum_removal()`)
  - Tier 2: PLSR on full ~330-band reflectance (scikit-learn `PLSRegression`)
  - Globe-LFMC 2.0 ground truth integration (SoCal chaparral observations loader)
  - LFMC map generation and uncertainty estimation (prediction intervals)
  - Validation: leave-one-site-out cross-validation, R², RMSE by vegetation type

### Track E: Validation & Cross-Comparison

- `src/tanager/validation.py` — **NEW** module for validation utilities
  - AVIRIS-3 Eaton Fire data ingestion (aggregate 3-4m fractions to 30m)
  - USGS BARC map loader and spatial alignment to Tanager grid
  - Globe-LFMC point extraction at Tanager pixel locations
  - Tanager vs EMIT/PRISMA quantitative comparison framework (for +5 tie-breaker)
  - Standard accuracy metrics: R², RMSE, MAE, bias, Kappa for classification
  - Scatterplot and residual diagnostic functions

## Impact

- **Affected specs:** None existing — new capability spec created
- **Affected code:** All new modules. Builds on Phase 2 modules (config, io, spectral, masks)
- **Dependencies introduced:** mesma>=1.0.8, spectral-libraries>=1.1.3, splib07-loader (GitHub)
- **Dependencies already present:** spectral (SPy), scikit-learn, scipy, xarray, numpy
- **Storage:** Endmember libraries ~100 MB; Globe-LFMC database ~50 MB; AVIRIS-3 validation ~2 GB

## Research Summary

Research is fully documented in `docs/research-memory.md` (v2.1). Key findings that shape this spec:

1. **MESMA is proven for spaceborne hyperspectral fire severity.** Quintano et al. (2023) achieved
   R²=0.64-0.79 vs CBI using PRISMA (240 bands, 12nm). Tanager-1 (426 bands, 5nm) should equal or
   exceed this because: (a) finer spectral sampling resolves more features, (b) the SWIR region
   2000-2300nm where char/ash signatures dominate has ~60 usable bands vs PRISMA's ~25.

2. **Endmember selection methodology is well-defined.** Roberts et al. (2018) established
   In-CoB + uSZU as the standard for post-fire MESMA. The FRAMES SoCal chaparral library (66 spectra)
   provides ground-truthed fire endmembers from the same ecoregion as our study area. `spectral-libraries`
   v1.1.3 implements EAR/MASA/CoB programmatically.

3. **No satellite hyperspectral LFMC product exists.** We would be first. PLSR achieves R²=0.72-0.94
   at leaf level (Peterson & Roberts 2014). Globe-LFMC 2.0 provides 287,551 field observations for
   training. The key wavelengths (970, 1200, 1660, 2100 nm) all fall within Tanager's usable spectrum.

4. **Validation data is available.** AVIRIS-3 Eaton Fire (ORNL DAAC, Jan 10-16 2025) provides
   high-resolution MESMA fractions for spatial validation. USGS BARC maps provide classified severity.
   Globe-LFMC 2.0 provides ground truth for LFMC regression.

5. **Risk: mesma v1.0.8 at 426 bands is untested.** Last updated Nov 2020, only 66 weekly downloads.
   HySUPP is the identified fallback. An early compatibility check is critical.

## Production Risk

Not applicable — this is a research project, not a production service.

## Open Questions for EM

1. **mesma v1.0.8 Python/numpy compatibility:** Last release was Nov 2020. Need to verify it works
   with Python 3.10+ and numpy 2.x before building the pipeline around it. If incompatible, pivot
   to HySUPP immediately.
2. **FRAMES SoCal library acquisition:** Need to confirm whether bulk download archive exists or
   if individual ASCII files must be scraped. May require manual data prep.
3. **Globe-LFMC 2.0 SoCal coverage:** Need to verify that sufficient observations exist within
   the LA fire study area for LFMC model training. If sparse, may need to expand to all California
   chaparral sites.
4. **AVIRIS-3 Eaton Fire public availability:** Confirm ORNL DAAC has released this dataset publicly
   and determine exact download mechanism.
5. **Shade endmember construction:** Is a single zero-reflectance spectrum sufficient, or do we
   need multiple shade endmembers representing different illumination geometries?
