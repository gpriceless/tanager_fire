"""Live Fuel Moisture Content (LFMC) products from Tanager-1 reflectance.

This module estimates per-pixel live fuel moisture from hyperspectral
reflectance using two complementary approaches:

* **Tier 1 — Spectral indices** (Quan et al. 2021):
  Eight water-sensitive indices computed by :func:`compute_lfmc_indices`,
  including SAI (Spectral Absorption Index) at 970, 1200, and 1660 nm,
  three NDWI variants (1240, 1640, 2130 nm), the Water Index WI = R900/R970,
  and continuum-removal band depths at the four water-absorption wavelengths.
  Indices are interpretable proxies for canopy water content but do not
  yield an absolute LFMC percent on their own.

* **Tier 2 — PLSRegression** (Peterson & Roberts 2014):
  :func:`train_lfmc_plsr` fits a Partial Least Squares regression from full
  ~330-band reflectance (bad bands removed) to ground-truth LFMC observations
  from Globe-LFMC 2.0. Returns the trained model plus 5-fold-CV R² / RMSE
  and per-band VIP (Variable Importance in Projection) scores so callers can
  verify the model is keying on water-absorption bands rather than spurious
  features.

* :func:`load_globe_lfmc` provides the ground-truth side: filtered
  GeoDataFrame of Globe-LFMC 2.0 observations, optionally restricted to a
  bounding box, vegetation types, or co-located with Tanager scene dates.

* :func:`predict_lfmc` applies a trained model to a scene and returns a
  per-pixel LFMC DataArray plus an uncertainty DataArray and a
  ``low_lfmc < 60%`` flag (the nonlinear regime per Roberts et al. 2006).

Heavy ML / vector imports (scikit-learn, geopandas) are deferred to function
bodies so importing :mod:`tanager.lfmc` stays cheap.

Public API (lazy-imported via :mod:`tanager`):

* :func:`compute_lfmc_indices`
* :func:`load_globe_lfmc`
* :func:`train_lfmc_plsr`
* :func:`predict_lfmc`

Import direction:

* lfmc.py MAY import from :mod:`tanager.config` and :mod:`tanager.spectral`
  (for ``continuum_removal``, ``select_bands``, and the
  ``_normalized_difference`` helper).
* lfmc.py MUST NOT import from :mod:`tanager.severity`,
  :mod:`tanager.unmixing`, :mod:`tanager.endmembers`, or
  :mod:`tanager.validation`.

References:
    Peterson, S. H., Roberts, D. A. (2014). Mapping live fuel moisture using
        partial least squares regression. Remote Sensing of Environment.
    Quan, X., He, B., Yebra, M., et al. (2021). A spectral absorption index
        for live fuel moisture content estimation. Remote Sensing.
    Roberts, D. A., Dennison, P. E., Roth, K. L. (2006). Methods for mapping
        live fuel moisture using AVIRIS data. International Journal of
        Wildland Fire.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Water-absorption band targets (nm)
# ---------------------------------------------------------------------------
# Centre wavelengths of the canonical liquid-water absorption features in the
# 0.9–2.2 µm region. These are nominal targets — actual band selection uses
# nearest-neighbour matching on the Tanager 5 nm grid.
_WATER_ABSORPTION_TARGETS_NM: Tuple[float, ...] = (970.0, 1200.0, 1660.0, 2100.0)

# Default left/right shoulder offsets for SAI computation, in nm.
# SAI fits a straight-line continuum between local maxima flanking the
# absorption feature. Offsets are searched within these windows.
_SAI_LEFT_WINDOW_NM: Tuple[float, float] = (-150.0, -20.0)
_SAI_RIGHT_WINDOW_NM: Tuple[float, float] = (20.0, 150.0)

# LFMC physical bounds (percent dry-mass basis).
# LFMC > 300% is unphysical (some succulents reach ~250%, but anything above
# 300% in a remotely-sensed pixel is a model artifact). Used to clip
# predict_lfmc output.
_LFMC_MIN_PERCENT: float = 0.0
_LFMC_MAX_PERCENT: float = 300.0

# The "low LFMC" flag threshold per Roberts et al. (2006):
# below 60% is the nonlinear / fire-prone regime where small moisture changes
# produce large changes in flammability. Used by predict_lfmc to set the
# `low_lfmc` boolean DataArray.
_LFMC_LOW_THRESHOLD_PERCENT: float = 60.0

# NDWI variants (numerator/denominator wavelength pairs in nm).
# Output convention: (R860 - Rtarget) / (R860 + Rtarget) so positive values
# indicate dry conditions and negative values wet.
_NDWI_PAIRS: Tuple[Tuple[str, float, float], ...] = (
    ("NDWI_1240", 860.0, 1240.0),
    ("NDWI_1640", 860.0, 1640.0),
    ("NDWI_2130", 860.0, 2130.0),
)

# Water Index numerator/denominator (Peñuelas et al. 1993):
# WI = R900 / R970. Values < 1 indicate water absorption.
_WI_NUMERATOR_NM: float = 900.0
_WI_DENOMINATOR_NM: float = 970.0


# ---------------------------------------------------------------------------
# Spectral Absorption Index (SAI) — core single-feature computation
# ---------------------------------------------------------------------------


def _compute_sai(
    reflectance: np.ndarray,
    wavelengths: np.ndarray,
    target_wl: float,
    left_shoulder: float,
    right_shoulder: float,
) -> float:
    """Compute the Spectral Absorption Index for a single feature.

    The SAI is the relative depth of a continuum-removed absorption feature:

    .. math::

        \\mathrm{SAI} = \\frac{R_c(\\lambda_t) - R(\\lambda_t)}{R_c(\\lambda_t)}

    where ``R_c`` is the straight-line continuum fit between the left and
    right shoulder reflectances and ``R(λ_t)`` is the measured reflectance
    at the absorption feature minimum.

    The output is clipped to ``[0, 1]``: 0 indicates no absorption (flat
    spectrum, or measured reflectance at or above the continuum), 1 indicates
    total absorption (zero reflectance at the feature minimum).

    Args:
        reflectance: 1-D array of reflectance values for a single pixel.
        wavelengths: 1-D wavelength array (nm), same length as ``reflectance``.
        target_wl: Wavelength of the absorption feature minimum (nm).
        left_shoulder: Approximate wavelength of the left continuum anchor (nm).
            Nearest-neighbour band matching (Tanager 5 nm grid) is applied so
            the value need only be approximate.
        right_shoulder: Approximate wavelength of the right continuum anchor (nm).

    Returns:
        SAI value in ``[0, 1]``. Returns ``0.0`` when the feature cannot be
        evaluated:

        * shoulders do not bracket the target (``left < target < right`` violated),
        * any of the target / shoulder wavelengths fall outside the supplied
          spectrum's range,
        * any of the three reflectance values is NaN,
        * the linearly-interpolated continuum is non-positive,
        * the measured reflectance at the target equals or exceeds the
          continuum (no absorption detected).

    Raises:
        ValueError: If ``reflectance`` and ``wavelengths`` have different shapes.
    """
    refl = np.asarray(reflectance, dtype=np.float64)
    wl = np.asarray(wavelengths, dtype=np.float64)

    if refl.shape != wl.shape:
        raise ValueError(
            f"reflectance shape {refl.shape} does not match wavelengths shape {wl.shape}"
        )
    if refl.ndim != 1:
        raise ValueError(
            f"_compute_sai expects 1-D arrays; got {refl.ndim}-D reflectance"
        )
    if refl.size == 0:
        return 0.0

    if not (left_shoulder < target_wl < right_shoulder):
        return 0.0

    wl_min = float(wl.min())
    wl_max = float(wl.max())
    if left_shoulder < wl_min or right_shoulder > wl_max:
        return 0.0

    idx_target = int(np.argmin(np.abs(wl - target_wl)))
    idx_left = int(np.argmin(np.abs(wl - left_shoulder)))
    idx_right = int(np.argmin(np.abs(wl - right_shoulder)))

    r_target = float(refl[idx_target])
    r_left = float(refl[idx_left])
    r_right = float(refl[idx_right])
    if not (np.isfinite(r_target) and np.isfinite(r_left) and np.isfinite(r_right)):
        return 0.0

    wl_left = float(wl[idx_left])
    wl_right = float(wl[idx_right])
    wl_target = float(wl[idx_target])
    if wl_right == wl_left:
        return 0.0

    continuum = r_left + (r_right - r_left) * (wl_target - wl_left) / (wl_right - wl_left)
    if continuum <= 0.0:
        return 0.0

    sai = (continuum - r_target) / continuum
    if not np.isfinite(sai):
        return 0.0
    return float(np.clip(sai, 0.0, 1.0))
