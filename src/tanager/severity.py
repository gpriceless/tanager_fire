"""Burn severity products from MESMA fraction maps.

This module turns per-pixel fractional abundance maps (char/PV/NPV/soil) into
burn severity products following Quintano et al. (2023):

* :func:`train_severity_model` — fit a regressor (default RF) from a 4-feature
  fraction matrix to ground-truth Composite Burn Index (CBI) values, with
  5-fold cross-validation R² / RMSE.
* :func:`predict_severity` — apply a trained model to produce a continuous CBI
  map (clipped to [0, 3]) plus a 5-class BARC severity map (Unburned / Low /
  Moderate-Low / Moderate-High / High).
* :func:`compute_trajectories` — run MESMA on a dictionary of dated scenes and
  stack the fraction outputs into a single time-series Dataset with dims
  (time, y, x).
* :func:`compare_severity_methods` — Pearson correlation, RMSE, bias, and
  difference map between a MESMA-derived severity product and a dNBR baseline.

Heavy ML imports (scikit-learn) are deferred to function bodies so that
importing :mod:`tanager.severity` stays cheap when only :func:`compute_trajectories`
is used.

Public API (lazy-imported via :mod:`tanager`):

* :func:`train_severity_model`
* :func:`predict_severity`
* :func:`compute_trajectories`
* :func:`compare_severity_methods`

Import direction:

* severity.py MAY import from :mod:`tanager.config`, :mod:`tanager.spectral`,
  and :mod:`tanager.unmixing` (for :func:`run_mesma` inside
  :func:`compute_trajectories`).
* severity.py MUST NOT import from :mod:`tanager.lfmc`,
  :mod:`tanager.endmembers`, or :mod:`tanager.validation`.

References:
    Quintano, C., Fernández-Manso, A., Roberts, D. A. (2023). Multiple
        Endmember Spectral Mixture Analysis (MESMA) for monitoring burn
        severity. Remote Sensing of Environment.
    Key, C. H., Benson, N. C. (2006). Landscape Assessment (LA): Sampling and
        Analysis Methods. USDA Forest Service General Technical Report.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BARC classification thresholds (Composite Burn Index → discrete severity)
# ---------------------------------------------------------------------------
# Standard BARC thresholds per Key & Benson (2006), used by USGS/USFS for
# operational classified burn severity maps. Codes are stored as int8 in the
# output severity_map; NaN inputs propagate to a sentinel value of -1 (handled
# explicitly by the caller).
_BARC_THRESHOLDS: Tuple[Tuple[float, int], ...] = (
    (0.10, 0),  # Unburned: CBI < 0.10
    (1.00, 1),  # Low:        0.10 <= CBI < 1.00
    (1.50, 2),  # Moderate-Low:  1.00 <= CBI < 1.50
    (2.25, 3),  # Moderate-High: 1.50 <= CBI < 2.25
    # High: CBI >= 2.25 → 4
)

# Fraction classes used as the feature vector when training/predicting CBI.
# Matches the canonical MESMA fraction order minus shade (which is removed
# by :func:`tanager.unmixing.normalize_fractions` before severity work).
_SEVERITY_FEATURES: Tuple[str, ...] = ("char", "pv", "npv", "soil")
