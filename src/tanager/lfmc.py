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
