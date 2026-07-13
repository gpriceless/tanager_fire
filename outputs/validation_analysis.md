# FireSpec Pipeline Output Analysis

**Date:** 2026-04-28
**Input:** 61 output files from `scripts/run_pipeline.py` (50 GeoTIFFs, 12 PNGs, 1 report)

## Executive Summary

The pipeline successfully exercised 15/15 stages across 3 real Tanager-1 scenes with zero errors. The core plumbing works — data loads, masks apply, indices compute, MESMA unmixes, and severity predicts. However, scientific analysis of the outputs reveals **6 issues** that must be resolved before any competition submission, ranging from incorrect dNBR temporal logic to MESMA fraction constraint violations.

**Verdict:** Pipeline **plumbing is validated.** Product outputs are **not submission-ready.** Specific gaps below.

---

## 1. What Was Produced

### Per-scene single-date products (3 scenes × N indices)

| Product | Scenes | Full-scene? | Coverage |
|---------|--------|-------------|----------|
| NBR | 3/3 | Yes | 30.7%, 67.5%, 75.8% valid pixels |
| NDVI | 3/3 | Yes | Same as NBR |
| NDWI | 3/3 | Yes | Same as NBR |
| SAI (970, 1200, 1660) | 3/3 | 256×256 crop | 100% of crop |
| NDWI variants (1240, 1640, 2130) | 3/3 | 256×256 crop | 28%-99% of crop |
| WI (Water Index) | 3/3 | 256×256 crop | 28%-99% of crop |
| CR depths (970, 1200, 1700, 2100) | 3/3 | 256×256 crop | 28%-99% of crop |

### Scene-specific products (20241215 only)

| Product | Notes |
|---------|-------|
| MESMA fractions (char, pv, npv, soil) | Image-derived endmembers, 94,795 valid pixels |
| MESMA RMSE | Mean 0.0099, all pixels < 0.025 |
| CBI map | Synthetic (3 × char), RF cv_r2=0.995 |
| Severity map | 5 classes (0-4) |

### Multi-scene products

| Product | Notes |
|---------|-------|
| dNBR (20250123→20250407) | 137,601 valid pixels, auto-aligned overlap |

---

## 2. Findings — Issues to Resolve

### ISSUE 1 — dNBR Temporal Logic Inverted (HIGH)

**Problem:** The dNBR is computed as `NBR(20250123) - NBR(20250407)` and is predominantly **negative** (mean = -0.177, 89.5% of pixels negative). By the USGS Key & Benson (2006) standard, positive dNBR indicates fire damage and negative indicates regrowth.

**What the data shows:** NBR increased from January to April (0.083 → 0.273 mean), consistent with spring green-up or post-fire vegetation recovery. Only 2.0% of pixels map to any burn severity class (Low or above).

**Root cause:** Both scenes are **post-fire.** The 20250123 scene was acquired during or shortly after the fire, and the 20250407 scene shows recovery. For valid burn severity mapping, the "pre" scene must be acquired **before the fire ignition date.**

**Impact:** The dNBR product as generated does not measure burn severity — it measures vegetation recovery. A true pre-fire scene is needed.

**Recommendation:** Source a pre-fire scene (before the fire ignition date for the Palisades/Hughes/Eaton fires, which started ~Jan 7, 2025). The 20241215 scene could potentially serve as pre-fire for the 20250123 area if their footprints overlap, but the report notes they are ~60 km apart.

---

### ISSUE 2 — MESMA Fractions Violate Non-Negativity Constraint (MEDIUM-HIGH)

**Problem:** MESMA fractions contain physically impossible values:
- **Negative fractions:** char has 5.2% negative, npv has 8.6% negative
- **Fractions > 1.0:** pv has 11.7% > 1.0, soil has 7.6% > 1.0
- **Range violations:** min = -0.25, max = 1.25

**Sum-to-one is enforced** (exactly 1.0000 for all pixels), but **non-negativity is not.**

**Root cause:** `normalize_fractions()` only applies shade removal + rescaling to sum=1.0. It does not clip or apply Fully Constrained Least Squares (FCLS). The underlying MESMA solver or NNLS fallback should produce non-negative fractions, but the shade normalization step (dividing by `1 - shade`) can amplify small negative residuals and push values above 1.0.

**Impact:** Downstream burn severity model trains on physically impossible fractions. The Random Forest will learn from the noise, inflating CV R² (currently 0.995 — suspiciously high even for synthetic ground truth).

**Recommendation:** Add a non-negativity clamp + re-normalize step in `normalize_fractions()`, or enforce FCLS constraints in the unmixing solver itself.

---

### ISSUE 3 — SAI1660 Produces All Zeros (MEDIUM)

**Problem:** The SAI at 1660 nm returns effectively zero for all three scenes (0, 24, and 491 non-zero pixels out of 65,536).

**Root cause:** The 1660 nm feature falls within the 1530–1790 nm atmospheric water absorption window. While the Tanager-1 surface reflectance product provides bands in this range (50 out of 52 bands are flagged as `good_wavelengths=1`), the reflectance values in this region are extremely low (~0.004). The SAI formula `(continuum - R_target) / continuum` requires the target band to show a **dip below** the interpolated continuum. In this spectral region, the overall signal is so weak and noisy that no consistent absorption dip appears — the target reflectance often meets or exceeds the continuum, producing SAI ≤ 0 which is clipped to 0.

**Impact:** SAI1660 is dead weight in any LFMC model. It adds a non-informative feature.

**Recommendation:** Either (a) remove SAI1660 from the feature set for Tanager data since the atmospheric correction doesn't preserve the 1660 nm water feature well enough, or (b) investigate whether a different continuum fitting approach (wider shoulders, or using continuum-removal depths instead) recovers the signal. The CR_depths_1700nm channel does show non-zero signal (mean 0.04–0.08), suggesting the hull-based approach handles this region better than the linear-shoulder SAI.

---

### ISSUE 4 — Severity Class 4 Out of CBI Range (LOW-MEDIUM)

**Problem:** The severity classification produces a class 4, but the CBI scale is bounded at 3.0 (Key & Benson 2006).

**Cause:** The `_BARC_THRESHOLDS` in `severity.py` define class 4 for CBI ≥ 2.25:
```
(0.10, 0),  # Unburned
(1.00, 1),  # Low
(1.50, 2),  # Moderate-Low
(2.25, 3),  # Moderate-High
# High: CBI >= 2.25 → 4
```

This is a 5-class BARC (Burned Area Reflectance Classification) scheme, not a CBI class scheme. The class numbering (0–4) is intentional in BARC, where 4 = "High severity." However, the report and PNG label this as "synthetic CBI", which conflates the two scales.

**Impact:** Labeling confusion. The CBI map values are [0, 3] as expected. The severity map values are [0, 4] which is correct for BARC. No computational bug, but the output naming is misleading.

**Recommendation:** Rename `severity.tif` to `barc_class.tif` or add metadata distinguishing CBI (continuous, 0–3) from BARC severity class (categorical, 0–4).

---

### ISSUE 5 — LFMC Indices on 256×256 Crop Only (KNOWN GAP)

**Problem:** All LFMC indices (SAI, NDWI variants, WI, CR depths) are computed on a 256×256 center crop — only ~7.7 km × 7.7 km at 30 m resolution. This is insufficient for a competition product.

**Root cause:** The continuum-removal step uses `xr.apply_ufunc(vectorize=True)`, iterating per-pixel in Python. This took >4 minutes on the full 20241215 scene and was killed by the pipeline timeout.

**Impact:** LFMC products don't cover the full burn scar. The center crop may not even overlap the fire-affected area.

**Coverage check for 20241215:**
- Full scene: 329,355 to 353,055 (E), 3,754,425 to 3,775,785 (N)
- 256×256 crop: 337,350 to 345,030 (E), 3,761,280 to 3,768,960 (N)
- The crop covers the center of the scene. From the NBR quicklook, the burn scar in 20241215 is in the upper-right quadrant — the LFMC crop may **partially miss** it.

**Recommendation:** Vectorize the continuum-removal hull computation (NumPy broadcasting or scipy.spatial.ConvexHull on the wavelength axis), or use dask chunking.

---

### ISSUE 6 — LFMC Coverage Disparity Between Index Types (LOW)

**Problem:** Within each scene's LFMC crop, SAI indices report 100% valid pixels (65,536/65,536) while NDWI/WI/CR indices report fewer (e.g., 18,366 for 20241215 = 28%).

**Root cause:** SAI uses a `clip(0, 1)` on the final output, so masked (NaN) pixels get treated as 0 rather than NaN. NDWI/WI/CR propagate NaN from masked reflectance bands. This means SAI has zero-filled regions where other indices have NaN — a silent inconsistency.

**Impact:** When stacking these indices for PLSR training, the zero-filled SAI pixels will bias the model if they're included in training but the corresponding NDWI/WI/CR values are NaN-dropped.

**Recommendation:** SAI should produce NaN for masked pixels rather than 0. Add a NaN guard before the clip: `xr.where(np.isfinite(r_target), sai, np.nan)`.

---

## 3. What Works Well

1. **Spectral indices (NBR, NDVI, NDWI)** — Value ranges are physically plausible. NBR ∈ [-0.85, 0.96], NDVI ∈ [-0.22, 1.0], NDWI ∈ [-0.95, 0.30]. All expected for mixed vegetation/bare soil/burn scar scenes.

2. **Temporal signal is ecologically coherent:** NDVI progresses 20250123 (0.32, winter/post-fire) → 20250407 (0.60, spring recovery) as expected. NBR shows the same pattern. The 20241215 scene (0.50 NDVI) fits its December timing.

3. **Masking pipeline** — Cloud, water, and nodata masks reduce valid pixel counts appropriately. 20241215 retains only 30.7% (consistent with the fragmented lower portion visible in quicklooks). The two later scenes retain 67-76%.

4. **MESMA RMSE is excellent** — Mean 0.0099 (< 1% reflectance error), 100% of pixels under 0.025. For image-derived endmembers this is a strong fit. The endmember selection heuristic (NBR/NDVI thresholds) found reasonable class regions: 7,871 char, 101,770 pv, 13,763 npv, 2,236 soil.

5. **Spatial alignment** — All products for a given scene share the same CRS (EPSG:32611), bounds, and 30 m resolution. Full-scene products (713×791 for 20241215) and LFMC crops (256×256) are correctly georeferenced.

6. **Continuum-removal depths show cross-scene variation** — CR_2100nm increases across scenes (0.164 → 0.191 → 0.225), possibly reflecting increasing vegetation water content from Dec → Jan → Apr. CR_970nm shows a similar pattern. This is a promising LFMC-predictive signal.

7. **Quicklooks are interpretable** — The NBR quicklook for 20241215 clearly shows a burn scar (red region, NBR < 0) in the upper-right quadrant surrounded by green vegetation. The 20250123 NBR shows a larger, more severe burn scar. The CBI quicklook identifies the burn scar region with elevated values.

---

## 4. Prioritized Gaps for Competition Readiness

| Priority | Gap | Required For | Effort |
|----------|-----|-------------|--------|
| P0 | Pre-fire scene for real dNBR | Burn severity product | Data sourcing |
| P0 | Vectorize LFMC continuum removal | Full-scene LFMC products | Engineering |
| P1 | MESMA non-negativity constraint | Reliable fraction maps | ~1 hr fix |
| P1 | ECOSTRESS / USGS endmember library | Publishable severity maps | Data acquisition + loader |
| P1 | CBI ground truth | Validated severity model | Field data or RAVG download |
| P2 | SAI1660 removal or rework | Clean LFMC feature set | ~30 min |
| P2 | SAI NaN handling fix | Consistent LFMC features | ~15 min |
| P2 | Severity class naming (CBI vs BARC) | Clear outputs | ~15 min |
| P3 | PLSR model training | predict_lfmc | Needs LFMC ground truth |

---

## 5. Data Inventory

- **Scenes analyzed:** 3 (20241215, 20250123, 20250407)
- **Total GeoTIFFs:** 50 (17 per scene for single-date, 1 dNBR, MESMA/severity for 20241215)
- **Total PNGs:** 12 (NBR/NDVI/NDWI quicklooks × 3 scenes, dNBR, CBI)
- **All CRS:** EPSG:32611 (UTM Zone 11N)
- **Spatial resolution:** 30 m
- **Report:** pipeline_report.md (accurate, well-structured)
