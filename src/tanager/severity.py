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
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

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

# Default RF hyperparameters per spec; deliberately conservative to avoid
# overfitting the small CBI ground-truth set typical for a single fire.
_DEFAULT_RF_N_ESTIMATORS: int = 200
_DEFAULT_RF_RANDOM_STATE: int = 42
_DEFAULT_CV_FOLDS: int = 5

# CBI is bounded in [0, 3] by Key & Benson (2006); RF can extrapolate
# slightly outside training range so we clip on prediction.
_CBI_MIN: float = 0.0
_CBI_MAX: float = 3.0


# ---------------------------------------------------------------------------
# Feature-matrix helpers
# ---------------------------------------------------------------------------


def _validate_features(
    fractions: xr.Dataset,
    feature_names: Sequence[str],
) -> None:
    """Check the requested feature variables are present in the fractions Dataset."""
    missing = [name for name in feature_names if name not in fractions.data_vars]
    if missing:
        raise ValueError(
            f"fractions Dataset is missing required variable(s): {missing}. "
            f"Available variables: {list(fractions.data_vars)}"
        )


def _flatten_fractions(
    fractions: xr.Dataset,
    feature_names: Sequence[str],
) -> Tuple[np.ndarray, Tuple[int, ...]]:
    """Stack the named fraction variables into an ``(n_pixels, n_features)`` matrix.

    Args:
        fractions: xarray Dataset with each feature variable shaped (y, x).
        feature_names: Variable names to stack, in feature order.

    Returns:
        Tuple of:
            X: ``(n_pixels, n_features)`` float64 array.
            spatial_shape: original ``(y, x)`` shape so callers can reshape
                predictions back to the scene grid.
    """
    _validate_features(fractions, feature_names)
    first = fractions[feature_names[0]]
    spatial_shape = tuple(first.shape)
    X = np.stack(
        [np.asarray(fractions[name].values, dtype=np.float64).ravel() for name in feature_names],
        axis=1,
    )
    return X, spatial_shape


def _coerce_target(
    target: Union[np.ndarray, xr.DataArray, xr.Dataset, Sequence[float]],
    expected_size: int,
) -> np.ndarray:
    """Coerce a CBI target into a flat float64 array and validate length."""
    if isinstance(target, xr.Dataset):
        raise TypeError(
            "ground_truth_cbi must be a 1-D array or DataArray, not a Dataset"
        )
    if isinstance(target, xr.DataArray):
        arr = np.asarray(target.values, dtype=np.float64).ravel()
    else:
        arr = np.asarray(target, dtype=np.float64).ravel()
    if arr.size != expected_size:
        raise ValueError(
            f"ground_truth_cbi has {arr.size} entries but fractions have "
            f"{expected_size} pixels; sizes must match (NaN target rows are "
            "filtered automatically)."
        )
    return arr


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train_severity_model(
    fractions: xr.Dataset,
    ground_truth_cbi: Union[np.ndarray, xr.DataArray, Sequence[float]],
    method: str = "random_forest",
    *,
    n_estimators: int = _DEFAULT_RF_N_ESTIMATORS,
    random_state: int = _DEFAULT_RF_RANDOM_STATE,
    cv_folds: int = _DEFAULT_CV_FOLDS,
    feature_names: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Train a fraction → CBI severity regressor with cross-validated metrics.

    Builds a per-pixel feature matrix from the supplied fraction maps
    (default features: char, pv, npv, soil) and fits a regressor that maps
    those four fractions to a Composite Burn Index value in ``[0, 3]``.
    Cross-validated R² and RMSE are reported on the held-out folds; the
    final model is then re-fit on all valid pixels and returned for use
    with :func:`predict_severity`.

    Args:
        fractions: xarray Dataset with each feature variable shaped (y, x).
            Typically the output of :func:`tanager.unmixing.normalize_fractions`
            (shade removed, remaining fractions sum to 1.0).
        ground_truth_cbi: 1-D array (or DataArray) of CBI values aligned with
            the flattened pixel order of ``fractions``. Length must equal
            ``y * x``. NaN entries in either ``fractions`` or
            ``ground_truth_cbi`` are masked out before training.
        method: Currently ``"random_forest"`` is the only supported method.
        n_estimators: Number of trees in the RF regressor. Default 200.
        random_state: Seed for RF determinism. Default 42.
        cv_folds: K for K-fold cross-validation. Default 5.
        feature_names: Optional override of the feature variables. Defaults
            to ``("char", "pv", "npv", "soil")``.

    Returns:
        Dict with keys:
            ``model``: trained ``RandomForestRegressor`` fit on all valid pixels.
            ``r2``: mean cross-validated R² (float).
            ``rmse``: cross-validated RMSE (float, in CBI units).
            ``method``: the method string used.
            ``feature_names``: tuple of feature variable names used.
            ``n_samples``: number of valid pixels used for training.

    Raises:
        ValueError: If ``method`` is unsupported, the fractions Dataset is
            missing a required feature variable, ``ground_truth_cbi`` length
            does not match the pixel count, or fewer than ``cv_folds`` valid
            pixels remain after NaN filtering.
    """
    if method != "random_forest":
        raise ValueError(
            f"unsupported method {method!r}; only 'random_forest' is implemented"
        )

    feats = tuple(feature_names) if feature_names is not None else _SEVERITY_FEATURES
    if not feats:
        raise ValueError("feature_names must contain at least one variable")

    X, _ = _flatten_fractions(fractions, feats)
    y = _coerce_target(ground_truth_cbi, X.shape[0])

    finite = np.all(np.isfinite(X), axis=1) & np.isfinite(y)
    n_valid = int(finite.sum())
    if n_valid < cv_folds:
        raise ValueError(
            f"only {n_valid} valid pixels after NaN filtering; need >= {cv_folds} "
            "for cross-validation"
        )

    X_train = X[finite]
    y_train = y[finite]

    # Heavy ML imports happen here so a bare `import tanager.severity` stays cheap.
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import cross_val_score

    model = RandomForestRegressor(
        n_estimators=n_estimators,
        random_state=random_state,
        n_jobs=-1,
    )

    r2_scores = cross_val_score(model, X_train, y_train, cv=cv_folds, scoring="r2")
    neg_mse_scores = cross_val_score(
        model, X_train, y_train, cv=cv_folds, scoring="neg_mean_squared_error"
    )
    r2 = float(np.mean(r2_scores))
    rmse = float(np.sqrt(-np.mean(neg_mse_scores)))

    # Refit on all valid samples so callers can immediately call predict_severity.
    model.fit(X_train, y_train)

    logger.info(
        "train_severity_model: method=%s n_samples=%d cv_r2=%.4f cv_rmse=%.4f",
        method,
        n_valid,
        r2,
        rmse,
    )

    return {
        "model": model,
        "r2": r2,
        "rmse": rmse,
        "method": method,
        "feature_names": feats,
        "n_samples": n_valid,
    }
