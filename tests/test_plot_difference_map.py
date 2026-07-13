"""Tests for plot_difference_map — dNBR raster with severity contour overlays.

Covers: return type, default USGS contours for dnbr, custom boundaries,
no contours for non-dnbr products without explicit boundaries,
NaN handling, publication mode, no-coords DataArray fallback.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest
import xarray as xr

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from tanager.visualization import PRODUCT_STYLES, plot_difference_map

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dnbr_da() -> xr.DataArray:
    """100×100 dNBR-like DataArray with gradient spanning -0.2 to 1.0 (covers all severity classes)."""
    x = np.linspace(340_000, 350_000, 100)
    y = np.linspace(3_780_000, 3_790_000, 100)
    data = np.linspace(-0.2, 1.0, 100 * 100).reshape(100, 100)
    return xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])


@pytest.fixture()
def dnbr_da_with_nan() -> xr.DataArray:
    """dNBR DataArray with a NaN patch in the centre."""
    x = np.linspace(340_000, 350_000, 100)
    y = np.linspace(3_780_000, 3_790_000, 100)
    data = np.linspace(-0.2, 1.0, 100 * 100).reshape(100, 100).copy()
    data[30:70, 30:70] = np.nan
    return xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])


@pytest.fixture()
def nbr_da() -> xr.DataArray:
    """NBR-like DataArray — product_name is not 'dnbr'."""
    x = np.linspace(340_000, 350_000, 60)
    y = np.linspace(3_780_000, 3_790_000, 60)
    data = np.random.default_rng(5).uniform(-0.5, 0.5, (60, 60))
    return xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapReturnType:
    """plot_difference_map must always return a matplotlib Figure."""

    def test_returns_figure_for_dnbr(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)

    def test_returns_figure_for_non_dnbr(self, nbr_da):
        fig = plot_difference_map(nbr_da, "nbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)

    def test_returns_figure_with_custom_boundaries(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr", class_boundaries={"Low": 0.1, "High": 0.5})
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# Default USGS contours for dnbr
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapDefaultContours:
    """For product_name='dnbr', contour lines must appear automatically."""

    def test_contours_present_for_dnbr_default(self, dnbr_da):
        """Axes collections must contain contour paths when dnbr is rendered."""
        fig = plot_difference_map(dnbr_da, "dnbr")
        ax = fig.axes[0]
        try:
            has_contours = any(
                hasattr(c, "get_paths") and len(c.get_paths()) > 0
                for c in ax.collections
            )
            assert has_contours, "Expected contour lines in ax.collections for dnbr"
        finally:
            plt.close(fig)

    def test_contour_labels_present_for_dnbr_default(self, dnbr_da):
        """ax.texts must contain at least one clabel annotation."""
        fig = plot_difference_map(dnbr_da, "dnbr")
        ax = fig.axes[0]
        try:
            assert len(ax.texts) > 0, "Expected at least one contour label text"
        finally:
            plt.close(fig)

    def test_colorbar_uses_dnbr_style(self, dnbr_da):
        """Colorbar label must reflect the dnbr PRODUCT_STYLES entry."""
        fig = plot_difference_map(dnbr_da, "dnbr")
        try:
            cb_ax = fig.axes[1]  # colorbar is the second axis
            assert PRODUCT_STYLES["dnbr"].label in cb_ax.get_ylabel()
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# Custom class boundaries
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapCustomBoundaries:
    """Explicitly supplied class_boundaries must override defaults."""

    def test_custom_boundaries_produce_contours(self, dnbr_da):
        boundaries = {"Light": 0.1, "Moderate": 0.4, "Severe": 0.8}
        fig = plot_difference_map(dnbr_da, "dnbr", class_boundaries=boundaries)
        ax = fig.axes[0]
        try:
            has_contours = any(
                hasattr(c, "get_paths") and len(c.get_paths()) > 0
                for c in ax.collections
            )
            assert has_contours, "Expected contours with custom boundaries"
        finally:
            plt.close(fig)

    def test_custom_boundaries_for_non_dnbr_product(self, nbr_da):
        """Custom boundaries should work for any product, not just dnbr."""
        boundaries = {"Negative": -0.2, "Positive": 0.2}
        fig = plot_difference_map(nbr_da, "nbr", class_boundaries=boundaries)
        ax = fig.axes[0]
        try:
            has_contours = any(
                hasattr(c, "get_paths") and len(c.get_paths()) > 0
                for c in ax.collections
            )
            assert has_contours, "Expected contours with custom boundaries on nbr"
        finally:
            plt.close(fig)

    def test_custom_boundaries_produce_labels(self, dnbr_da):
        """Each custom boundary class name should appear as a clabel annotation."""
        boundaries = {"A": 0.1, "B": 0.5}
        fig = plot_difference_map(dnbr_da, "dnbr", class_boundaries=boundaries)
        ax = fig.axes[0]
        try:
            # At least one label text must exist
            assert len(ax.texts) > 0, "Expected clabel annotations with custom boundaries"
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# No contours for non-dnbr without explicit boundaries
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapNoContoursForOtherProducts:
    """For products other than 'dnbr', contours must NOT appear without explicit boundaries."""

    def test_no_contours_for_nbr_without_boundaries(self, nbr_da):
        fig = plot_difference_map(nbr_da, "nbr")
        ax = fig.axes[0]
        try:
            paths_with_content = [
                c for c in ax.collections
                if hasattr(c, "get_paths") and len(c.get_paths()) > 0
            ]
            assert len(paths_with_content) == 0, (
                "Expected no contours for nbr without explicit class_boundaries"
            )
        finally:
            plt.close(fig)

    def test_no_contours_for_ndvi_without_boundaries(self):
        x = np.linspace(340_000, 350_000, 50)
        y = np.linspace(3_780_000, 3_790_000, 50)
        data = np.linspace(-1.0, 1.0, 50 * 50).reshape(50, 50)
        da = xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])

        fig = plot_difference_map(da, "ndvi")
        ax = fig.axes[0]
        try:
            paths_with_content = [
                c for c in ax.collections
                if hasattr(c, "get_paths") and len(c.get_paths()) > 0
            ]
            assert len(paths_with_content) == 0, (
                "Expected no contours for ndvi without explicit class_boundaries"
            )
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# NaN handling
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapNaNHandling:
    """DataArrays with NaN values must render without error."""

    def test_partial_nan_renders_without_error(self, dnbr_da_with_nan):
        fig = plot_difference_map(dnbr_da_with_nan, "dnbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)

    def test_all_nan_renders_without_error(self, dnbr_da):
        all_nan = dnbr_da.copy(data=np.full(dnbr_da.shape, np.nan))
        fig = plot_difference_map(all_nan, "dnbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# Publication mode
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapPublicationMode:
    """publication=True must set figure DPI to 300."""

    def test_publication_sets_dpi_300(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr", publication=True)
        try:
            assert fig.get_dpi() == 300
        finally:
            plt.close(fig)

    def test_non_publication_does_not_force_dpi_300(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr", publication=False)
        try:
            assert fig.get_dpi() != 300
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# figsize
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapFigsize:
    def test_custom_figsize_applied(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr", figsize=(6, 5))
        try:
            w, h = fig.get_size_inches()
            assert abs(w - 6) < 0.01
            assert abs(h - 5) < 0.01
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# No-coordinates fallback
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapNoCoords:
    """DataArrays without x/y coordinates must render without error (pixel-space contours)."""

    def test_no_coords_does_not_raise(self):
        data = np.linspace(-0.2, 1.0, 40 * 40).reshape(40, 40)
        da = xr.DataArray(data)
        fig = plot_difference_map(da, "dnbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)

    def test_no_coords_contours_still_drawn(self):
        """Contours should still be drawn even without geo coordinates."""
        data = np.linspace(-0.2, 1.0, 40 * 40).reshape(40, 40)
        da = xr.DataArray(data)
        fig = plot_difference_map(da, "dnbr")
        ax = fig.axes[0]
        try:
            has_contours = any(
                hasattr(c, "get_paths") and len(c.get_paths()) > 0
                for c in ax.collections
            )
            assert has_contours, "Expected contour lines even without geo coordinates"
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# UTM axes on georef input
# ---------------------------------------------------------------------------


class TestPlotDifferenceMapUTMAxes:
    """With UTM coordinates, axes labels must reflect geo space."""

    def test_xlabel_easting(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr")
        ax = fig.axes[0]
        try:
            assert ax.get_xlabel() == "Easting (km)"
        finally:
            plt.close(fig)

    def test_ylabel_northing(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr")
        ax = fig.axes[0]
        try:
            assert ax.get_ylabel() == "Northing (km)"
        finally:
            plt.close(fig)

    def test_xlim_is_utm_metres(self, dnbr_da):
        fig = plot_difference_map(dnbr_da, "dnbr")
        ax = fig.axes[0]
        try:
            xlo, xhi = ax.get_xlim()
            assert xlo > 100_000, f"xlim lower {xlo} looks like pixel-space"
        finally:
            plt.close(fig)
