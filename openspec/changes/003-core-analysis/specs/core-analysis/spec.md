# Capability: Core Analysis — MESMA Spectral Unmixing & LFMC Estimation

**Capability ID:** core-analysis
**Version:** 1.0.0
**Change:** 003-core-analysis
**Date:** 2026-04-27

---

## Overview

This capability adds spectral unmixing (MESMA), burn severity mapping, and live fuel moisture
content estimation to the Tanager pipeline. It transforms preprocessed hyperspectral imagery
into actionable wildfire products: fraction maps, severity classifications, and LFMC estimates.

---

## ADDED Requirements

### Requirement: Endmember Library Loading

The system SHALL load spectral endmember libraries from multiple sources and resample them to
Tanager-1 band centers for use in spectral unmixing.

#### Scenario: Load USGS Spectral Library v7

WHEN `load_usgs_library(categories=["char", "soil", "vegetation"])` is called
THEN the system SHALL return an xarray DataArray with dims `(spectrum_id, wavelength)`
AND wavelength coordinate SHALL span 380-2500 nm at source resolution (1 nm)
AND each spectrum SHALL have metadata attributes: name, category, source
AND spectra with all-NaN values in the VSWIR range SHALL be excluded

#### Scenario: Load ECOSTRESS library via SPy

WHEN `load_ecostress_library(categories=["vegetation", "npv", "mineral"])` is called
THEN the system SHALL load spectra via SPy's `EcostressDatabase` interface
AND return an xarray DataArray with the same schema as USGS library output
AND only VSWIR spectra (0.35-2.5 um) SHALL be included (exclude TIR)

#### Scenario: Load FRAMES SoCal chaparral library

WHEN `load_frames_library(data_dir=path)` is called
THEN the system SHALL parse ASCII spectral files from the FRAMES collection
AND return endmembers categorized as: char, ash, pv, npv, soil
AND metadata SHALL include species name, collection site, fire name

#### Scenario: Resample library to Tanager band centers

WHEN `resample_library(library, target_wavelengths, fwhm=5.5)` is called
THEN the system SHALL apply Gaussian FWHM convolution via SPy `BandResampler`
AND output wavelengths SHALL match Tanager-1 band centers (from scene metadata)
AND output spectral sampling SHALL be ~5 nm
AND reflectance values outside [0, 1] after resampling SHALL be clipped

---

### Requirement: Endmember Selection

The system SHALL select an optimal subset of endmembers from the full library to minimize
spectral redundancy while maximizing class separability.

#### Scenario: In-CoB count-based selection

WHEN `select_endmembers_incob(library, max_per_class)` is called
THEN the system SHALL compute Count-Based selection within each endmember class
AND return at most `max_per_class` endmembers per class
AND selection SHALL favor spectra that model the most image pixels (highest count)
AND the output SHALL preserve class labels and metadata

#### Scenario: EAR/MASA joint pruning

WHEN `prune_endmembers_ear_masa(library, threshold_ear, threshold_masa)` is called
THEN the system SHALL apply EAR (Endmember Average RMSE) and MASA (Minimum Average Spectral Angle) metrics
AND endmembers that exceed both thresholds SHALL be removed
AND implementation SHALL use `spectral-libraries` v1.1.3 `EarMasaCob` class
AND the pruned library SHALL contain between 50 and 80 spectra total

#### Scenario: Image-derived endmember extraction

WHEN `extract_image_endmembers(scene, method="spatial", regions=dict)` is called
THEN the system SHALL extract endmember spectra from specified pixel regions in a Tanager scene
AND extracted spectra SHALL be averaged over each region (mean spectrum)
AND output format SHALL match the library DataArray schema
AND method "spatial" SHALL use user-defined ROI coordinates
AND method "ppi" SHALL use Pixel Purity Index algorithm (via SPy)

---

### Requirement: MESMA Spectral Unmixing

The system SHALL perform Multiple Endmember Spectral Mixture Analysis on Tanager imagery,
producing per-pixel fractional abundance maps for fire-relevant endmember classes.

#### Scenario: Run MESMA on a Tanager scene

WHEN `run_mesma(scene, library, constraints)` is called
THEN the system SHALL unmix each pixel using combinations from the endmember library
AND output SHALL be an xarray Dataset with fraction variables: char, pv, npv, soil, shade
AND fractions SHALL sum to 1.0 (within tolerance of 0.01)
AND the RMSE of the best-fit model SHALL be stored as a variable in the output Dataset
AND pixels where no model passes constraints SHALL have NaN fractions

#### Scenario: uSZU band selection before unmixing

WHEN `select_bands_uszu(scene, library, n_bands=40)` is called
THEN the system SHALL select the top `n_bands` most discriminatory bands using Uniform SZU criterion
AND output SHALL be a band-subset of the input scene (xarray Dataset with reduced wavelength dim)
AND selected bands SHALL maximize class separability across all endmember classes

#### Scenario: RMSE constraint filtering

WHEN MESMA is executed with `constraints={"max_rmse": 0.025, "min_fraction": -0.05, "max_fraction": 1.05}`
THEN only models with RMSE <= max_rmse SHALL be accepted
AND fraction values outside [min_fraction, max_fraction] SHALL disqualify a model
AND the best-fitting valid model (lowest RMSE) SHALL be selected for each pixel

#### Scenario: Shade normalization

WHEN `normalize_fractions(fractions, remove_shade=True)` is called
THEN shade fraction SHALL be removed from the output
AND remaining fractions SHALL be rescaled to sum to 1.0
AND output variable names SHALL be: char, pv, npv, soil (no shade)

#### Scenario: MESMA fallback to HySUPP

WHEN the `mesma` package fails to import or raises a compatibility error at 426 bands
THEN the system SHALL log a warning and fall back to HySUPP's FCLS unmixing
AND output format SHALL remain identical (same DataArray schema)
AND a metadata attribute `unmixing_engine` SHALL record which backend was used

---

### Requirement: Burn Severity Mapping

The system SHALL derive burn severity products from MESMA fraction maps, producing
classified severity maps and continuous CBI-equivalent estimates.

#### Scenario: Train severity regression model

WHEN `train_severity_model(fractions, ground_truth_cbi, method="random_forest")` is called
THEN the system SHALL train a Random Forest regressor (scikit-learn)
AND features SHALL be: char fraction, NPV fraction, PV fraction, soil fraction (4 features)
AND target SHALL be CBI values (continuous, 0-3 scale)
AND the trained model SHALL be returned along with cross-validation R² and RMSE
AND default hyperparameters: n_estimators=200, max_depth=None, random_state=42

#### Scenario: Predict severity from fractions

WHEN `predict_severity(fractions, model)` is called
THEN the system SHALL apply the trained model to produce a continuous CBI estimate per pixel
AND output SHALL be an xarray DataArray with dims (y, x) and values in [0, 3]
AND a classified severity map SHALL also be produced using USGS BARC thresholds:
  - Unburned: CBI < 0.1
  - Low: 0.1 <= CBI < 1.0
  - Moderate-Low: 1.0 <= CBI < 1.5
  - Moderate-High: 1.5 <= CBI < 2.25
  - High: CBI >= 2.25

#### Scenario: Multi-temporal fraction trajectories

WHEN `compute_trajectories(scenes_dict, library)` is called with a dict of {date: scene} pairs
THEN the system SHALL run MESMA on each scene using the same endmember library
AND output SHALL be an xarray Dataset with dims (time, y, x) and fraction variables
AND the time coordinate SHALL be derived from scene datetime metadata
AND at minimum, the pre-fire (Dec 2024) and post-fire (Jan 2025) pair SHALL be included

#### Scenario: dNBR baseline comparison

WHEN `compare_severity_methods(mesma_severity, dnbr_severity)` is called
THEN the system SHALL compute agreement statistics between MESMA-derived and dNBR-derived severity
AND output SHALL include: correlation coefficient, RMSE, bias, and a difference map
AND the comparison SHALL demonstrate MESMA's improvement over broadband dNBR

---

### Requirement: LFMC Estimation

The system SHALL estimate live fuel moisture content from Tanager hyperspectral imagery using
spectral water absorption features and multivariate regression.

#### Scenario: Compute spectral absorption indices

WHEN `compute_lfmc_indices(scene)` is called
THEN the system SHALL compute the following water-sensitive indices:
  - SAI970: Spectral Absorption Index at 970 nm
  - SAI1200: Spectral Absorption Index at 1200 nm
  - SAI1660: Spectral Absorption Index at 1660 nm
  - NDWI_1240: (R860 - R1240) / (R860 + R1240)
  - NDWI_1640: (R860 - R1640) / (R860 + R1640)
  - NDWI_2130: (R860 - R2130) / (R860 + R2130)
  - WI: R900 / R970
  - CR_depths: continuum removal band depths at 970, 1200, 1700, 2100 nm
AND output SHALL be an xarray Dataset with each index as a variable (dims: y, x)
AND all wavelength lookups SHALL use nearest-neighbor matching (Tanager 5nm grid)

#### Scenario: SAI computation method

WHEN computing SAI at a target wavelength (e.g., 1200 nm)
THEN the system SHALL:
  1. Identify the absorption feature minimum near the target wavelength
  2. Identify left and right shoulder wavelengths (local maxima flanking the feature)
  3. Compute the straight-line continuum between shoulders
  4. SAI = (continuum_at_target - reflectance_at_target) / continuum_at_target
AND SAI values SHALL be in [0, 1] (0 = no absorption, 1 = complete absorption)
AND if no clear absorption feature is detected, SAI SHALL be set to 0.0

#### Scenario: PLSR LFMC regression

WHEN `train_lfmc_plsr(spectra, lfmc_values, n_components=10)` is called
THEN the system SHALL train a Partial Least Squares Regression model (scikit-learn PLSRegression)
AND input spectra SHALL be the full ~330-band reflectance (bad bands excluded)
AND target SHALL be LFMC values in percent (typically 30-200%)
AND the model SHALL be returned along with: R², RMSE, optimal n_components (via cross-validation)
AND feature importance (VIP scores) SHALL be computed to identify key wavelengths

#### Scenario: Globe-LFMC ground truth loading

WHEN `load_globe_lfmc(region_bbox, vegetation_types=["chaparral"])` is called
THEN the system SHALL load Globe-LFMC 2.0 observations within the spatial bounding box
AND filter to specified vegetation types
AND return a GeoDataFrame with columns: longitude, latitude, date, lfmc_percent, species, site_name
AND observations co-located with Tanager scene dates (within +-30 days) SHALL be flagged

#### Scenario: LFMC prediction and uncertainty

WHEN `predict_lfmc(scene, model, method="plsr")` is called
THEN the system SHALL produce a per-pixel LFMC estimate (% dry weight)
AND output SHALL be an xarray DataArray with dims (y, x)
AND uncertainty estimates (prediction intervals) SHALL be provided as a second DataArray
AND pixels with LFMC < 60% SHALL be flagged (nonlinear regime per Roberts et al. 2006)

---

### Requirement: Validation Framework

The system SHALL provide standardized validation tools for comparing model outputs against
reference datasets and computing accuracy metrics.

#### Scenario: Load AVIRIS-3 Eaton Fire reference

WHEN `load_aviris3_reference(filepath, target_resolution=30)` is called
THEN the system SHALL load AVIRIS-3 fraction maps
AND aggregate from native resolution (3-4 m) to target resolution (30 m) by spatial averaging
AND output SHALL be an xarray Dataset with the same fraction variable names as MESMA output
AND spatial alignment to Tanager grid SHALL use nearest-neighbor resampling

#### Scenario: Load USGS BARC maps

WHEN `load_barc_reference(filepath)` is called
THEN the system SHALL load classified burn severity maps from USGS Burn Severity Portal
AND output SHALL be an xarray DataArray with severity classes as integer codes
AND spatial alignment to Tanager grid SHALL be performed

#### Scenario: Compute accuracy metrics

WHEN `compute_accuracy(predicted, observed, metric_type="continuous")` is called
THEN for continuous data the system SHALL compute: R², RMSE, MAE, bias, and Spearman correlation
AND for classified data (`metric_type="classified"`) SHALL compute: overall accuracy, Kappa, confusion matrix, per-class F1
AND output SHALL be a dictionary of metric names to values

#### Scenario: Tanager vs EMIT/PRISMA comparison

WHEN `compare_sensors(tanager_result, reference_result, sensor_name)` is called
THEN the system SHALL compute comparative accuracy metrics between Tanager-derived products and reference sensor products
AND output SHALL include improvement ratios (e.g., R² improvement over broadband)
AND a structured comparison table suitable for the competition submission SHALL be generated

---

## Dependencies on Phase 2 Modules

| Module | Usage in Phase 3 |
|--------|-------------------|
| `config.py` | SENSOR params, BAD_BAND_RANGES, FIRE_SCENES, BAND_ALIASES, DATA_DIR |
| `catalog.py` | Download scenes for multi-temporal analysis |
| `io.py` | Load scenes via `load_scene()` |
| `spectral.py` | `mask_bad_bands()`, `select_bands()`, `continuum_removal()`, `nbr()`, `dnbr()` |
| `masks.py` | `nodata_mask()`, `cloud_mask()`, `apply_masks()` before analysis |

---

## Non-Functional Requirements

### Performance

- MESMA unmixing on a single Tanager scene (~1000x1000 pixels, 40 bands, 78 endmembers) SHALL
  complete within 30 minutes on a single CPU core
- LFMC index computation SHALL complete within 60 seconds per scene
- Endmember library resampling SHALL complete within 10 seconds for 100 spectra

### Reproducibility

- All random operations (RF, train/test splits) SHALL use fixed seeds (default: 42)
- Model training functions SHALL return the model object for serialization via joblib
- All intermediate products SHALL be expressible as xarray Datasets with full metadata

### Compatibility

- All new modules SHALL work with Python 3.10+
- All functions SHALL accept xarray Datasets produced by `tanager.io.load_scene()`
- Wavelengths SHALL always be in nanometers (nm), consistent with Phase 2 convention
- Fraction maps SHALL use the same spatial coordinate system as the input scene
