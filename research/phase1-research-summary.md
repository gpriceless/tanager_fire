# Phase 1 Research Summary: FireSpec Literature Review & Tool Evaluation

**Date:** 2026-04-27
**Author:** Tobler (Research Lead)
**Status:** Complete
**Handoff to:** Product Queen (for OpenSpec change proposal)

---

## Executive Summary

Phase 1 research validates the FireSpec approach with high confidence. The literature provides a clear methodological template (Quintano et al. 2023), proven ~2x accuracy improvement over broadband sensors, and a gap we can fill: no satellite hyperspectral LFMC product exists. Tanager-1's 426-band sensor at 5nm spacing is the finest spectral resolution in orbit, making 20+ years of AVIRIS fire research directly transferable. The LA wildfire time series (7 scenes, Palisades + Eaton fires) provides a compelling, timely case study with available validation data (AVIRIS-3, BARC maps).

**Bottom line:** We have strong science, available tools, available data, and a genuine novelty gap to fill. Proceed to Phase 2.

---

## Key Findings by Research Track

### 1. Burn Severity via MESMA

**Validated approach:** Quintano et al. (2023) demonstrated that MESMA on spaceborne hyperspectral (PRISMA, 239 bands, 30m) achieves R2=0.64-0.79 for burn severity vs field-measured CBI. Sentinel-2 achieves only R2=0.27-0.53 on the same fires. This ~2x improvement is the core value proposition.

**Methodology:** Load Tanager L2 surface reflectance -> bad band mask -> uSZU band selection (~30-50 diagnostic bands) -> MESMA unmixing into char/PV/NPV/soil/shade fractions -> Random Forest regression to CBI-equivalent severity -> validate against AVIRIS-3 and BARC maps.

**Endmembers:** FRAMES Burn Severity Spectral Library provides fire-specific endmembers from SoCal chaparral (char, ash, GV, NPV, soil). Supplement with ECOSTRESS library and image-derived endmembers.

**Multi-temporal opportunity:** The 7-scene time series enables fraction trajectory analysis (char decrease, GV increase) from Dec 2024 to Jul 2025 — a recovery narrative that single-date studies lack.

### 2. Live Fuel Moisture Content (LFMC)

**Novel contribution:** No satellite hyperspectral LFMC product exists from any spaceborne imaging spectrometer. We would be first. AVIRIS airborne work by Roberts, Dennison, and Peterson built extensive SoCal chaparral LFMC knowledge that transfers directly to Tanager.

**Recommended approach (two-tier):**
- **Tier 1 (indices):** SAI1200 for EWT (R2cv=0.845), SAI1660 for FMC (R2cv=0.637), NDWI variants, continuum-removal band depth
- **Tier 2 (ML):** PLSR using full 330-band reflectance, expected R2=0.70-0.94

**Key advantage:** Tanager's 5nm sampling resolves water absorption features at 970, 1200, 1700, and 2100nm that broadband sensors average away. Hyperspectral explains ~25% more variability than broadband for vegetation biophysical properties.

**Training data:** Globe-LFMC 2.0 (287,551 field observations, heavy US coverage). Need to verify SoCal chaparral coverage.

### 3. Tanager-1 Sensor Characterization

- 426 bands, 380-2500nm, 5nm sampling, 5.5nm FWHM — finest spectral resolution in orbit
- SNR 310-655 at 2200nm (mode-dependent), claimed 3-6x more sensitive than comparable systems
- ISOFIT v2.9.5 atmospheric correction achieves ~1% RMSE — L2 products are analysis-ready
- Bad band masking removes ~80-90 bands in atmospheric absorption windows, leaving ~330-346 usable
- 30m GSD = landscape-scale burn severity (matching Landsat dNBR standard), not structure-level

### 4. Tool Evaluation

| Tool | Verdict | Key Issue |
|------|---------|-----------|
| HyperCoast v0.20.2 | **USE** — primary loader | Ortho products only (Basic needs gridding) |
| SPy v0.24 | **USE** — most mature | Needs numpy bridge from xarray |
| MESMA v1.0.8 | **USE with caution** | Last updated 2020; test 426-band performance |
| HySUPP | **FALLBACK** | Alternative unmixing if MESMA fails |
| spyndex v0.6.0 | **USE** | 232+ indices, any numpy input |
| pystac | **USE** | Static STAC catalog (not API) |

**Integration architecture:** HyperCoast (HDF5 -> xarray) -> numpy bridge -> SPy/MESMA/spyndex

---

## Validation Strategy

| Source | What It Validates | Resolution | Access |
|--------|------------------|-----------|--------|
| AVIRIS-3 Eaton Fire (Jan 2025) | Burn severity fractions at high-res | 3-4 m | ORNL DAAC |
| USGS Burn Severity Portal v11.0 | BARC severity classification | 30 m | usgs.gov |
| Globe-LFMC 2.0 | LFMC field measurements | Point | Open data |
| Sentinel-2 dNBR | Broadband baseline to beat | 10-20 m | Copernicus |

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MESMA fails at 426 bands | Medium | High | uSZU band reduction to ~30-50 bands; HySUPP fallback |
| No CBI field data for LA fires | Medium | Medium | Use BARC maps + AVIRIS-3 as proxy |
| Globe-LFMC 2.0 lacks SoCal coverage | Low | Medium | Use Roberts et al. published calibration coefficients |
| STAC catalog changes or goes offline | Low | Low | Cache scene metadata locally |
| Smoke in post-fire scenes degrades ISOFIT | Medium | Low | Focus on pre-fire and recovery scenes; flag affected pixels |

---

## Recommended Phase 2 Scope

1. **Data pipeline:** STAC catalog query -> scene inventory -> HDF5 download -> preprocessing (bad band mask, cloud mask, gridding)
2. **Exploratory analysis:** Load one pre-fire and one post-fire scene; compute basic indices (NBR, NDVI, NDWI); visualize spectral signatures of burned vs unburned pixels
3. **Endmember library:** Download FRAMES library; resample to Tanager bands via SPy BandResampler; extract image-derived endmembers
4. **MESMA feasibility test:** Run MESMA on a small spatial subset (100x100 pixels) with 4-5 endmembers; measure runtime and accuracy

---

## Key References (Most Critical)

- Quintano et al. (2023) RSE — PRISMA MESMA fire severity (DOI: 10.1016/j.rse.2023.113670)
- Roberts et al. (2018) RS — Endmember/band selection for MESMA (DOI: 10.3390/rs10030389)
- Veraverbeke et al. (2018) RSE — Hyperspectral fire RS review (DOI: 10.1016/j.rse.2018.06.020)
- Roberts et al. (2006) JGR — AVIRIS LFMC in SoCal chaparral (DOI: 10.1029/2005JG000113)
- Quan et al. (2021) PLOS ONE — SAI indices for water content (DOI: 10.1371/journal.pone.0249351)
- Yebra et al. (2024) Sci Data — Globe-LFMC 2.0 (DOI: 10.1038/s41597-024-03159-6)
- Ward-Baranyay, Coleman et al. (2026) GRL (DOI: 10.1029/2025GL118756)

Full literature tables in `docs/research-memory.md`.
