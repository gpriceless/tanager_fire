"""Tests for add_basemap — contextily tile overlay.

All tests mock ``contextily.add_basemap`` to avoid network dependencies.
The tests verify that:
- The correct provider is selected for each source string.
- Unknown source strings fall back to satellite with a warning.
- Network failures (exceptions from ctx.add_basemap) are caught and logged.
- The function always returns the axes object.
- plot_map calls add_basemap when basemap=True.
"""

from __future__ import annotations

from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")  # non-interactive backend before pyplot import

import matplotlib.pyplot as plt
import numpy as np
import pytest
import xarray as xr

from tanager.visualization import add_basemap, plot_map

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ax():
    """A matplotlib Axes with UTM-like extent already set."""
    fig, ax = plt.subplots()
    ax.set_xlim(340_000, 350_000)
    ax.set_ylim(3_780_000, 3_790_000)
    yield ax
    plt.close(fig)


@pytest.fixture()
def utm_da() -> xr.DataArray:
    """50×50 DataArray with UTM x/y coordinates (EPSG:32611 region)."""
    x = np.linspace(340_000, 350_000, 50)
    y = np.linspace(3_780_000, 3_790_000, 50)
    data = np.random.default_rng(0).random((50, 50)).astype(np.float32)
    return xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])


# ---------------------------------------------------------------------------
# add_basemap — return value
# ---------------------------------------------------------------------------


class TestAddBasemapReturnsAxes:
    """add_basemap must always return the axes object."""

    def test_returns_ax_on_success(self, ax):
        with patch("contextily.add_basemap"):
            result = add_basemap(ax)
        assert result is ax

    def test_returns_ax_on_network_failure(self, ax):
        with patch("contextily.add_basemap", side_effect=OSError("network error")):
            result = add_basemap(ax)
        assert result is ax

    def test_returns_ax_for_unknown_source(self, ax):
        with patch("contextily.add_basemap"):
            result = add_basemap(ax, source="unknown_provider")
        assert result is ax


# ---------------------------------------------------------------------------
# add_basemap — contextily.add_basemap is called
# ---------------------------------------------------------------------------


class TestAddBasemapCallsContextily:
    """contextily.add_basemap must be called with the correct arguments."""

    def test_satellite_source_calls_contextily(self, ax):
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, source="satellite")
        assert mock_ctx.called

    def test_osm_source_calls_contextily(self, ax):
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, source="osm")
        assert mock_ctx.called

    def test_terrain_source_calls_contextily(self, ax):
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, source="terrain")
        assert mock_ctx.called

    def test_default_call_passes_crs(self, ax):
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax)
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("crs") == "EPSG:32611"

    def test_custom_crs_forwarded(self, ax):
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, crs="EPSG:4326")
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("crs") == "EPSG:4326"

    def test_alpha_forwarded(self, ax):
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, alpha=0.7)
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("alpha") == pytest.approx(0.7)

    def test_zorder_is_zero(self, ax):
        """Basemap must be at zorder=0 so raster renders on top."""
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax)
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("zorder") == 0


# ---------------------------------------------------------------------------
# add_basemap — provider selection
# ---------------------------------------------------------------------------


class TestAddBasemapProviderSelection:
    """The source string must select the correct contextily provider."""

    def test_satellite_uses_esri_world_imagery(self, ax):
        import contextily as ctx
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, source="satellite")
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("source") == ctx.providers.Esri.WorldImagery

    def test_osm_uses_openstreetmap_mapnik(self, ax):
        import contextily as ctx
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, source="osm")
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("source") == ctx.providers.OpenStreetMap.Mapnik

    def test_terrain_uses_stadia_stamen_terrain(self, ax):
        import contextily as ctx
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, source="terrain")
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("source") == ctx.providers.Stadia.StamenTerrain

    def test_unknown_source_falls_back_to_satellite(self, ax):
        import contextily as ctx
        with patch("contextily.add_basemap") as mock_ctx:
            add_basemap(ax, source="nonexistent")
        _, kwargs = mock_ctx.call_args
        assert kwargs.get("source") == ctx.providers.Esri.WorldImagery


# ---------------------------------------------------------------------------
# add_basemap — error handling
# ---------------------------------------------------------------------------


class TestAddBasemapErrorHandling:
    """Network and tile-fetch failures must be swallowed with a warning log."""

    def test_network_oserror_does_not_raise(self, ax):
        with patch("contextily.add_basemap", side_effect=OSError("connection timed out")):
            # Should not raise
            add_basemap(ax)

    def test_network_exception_does_not_raise(self, ax):
        with patch("contextily.add_basemap", side_effect=Exception("tile server unavailable")):
            add_basemap(ax)

    def test_network_failure_logs_warning(self, ax, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="tanager.visualization"):
            with patch("contextily.add_basemap", side_effect=OSError("timeout")):
                add_basemap(ax)
        assert any("basemap" in record.message.lower() for record in caplog.records)

    def test_unknown_source_logs_warning(self, ax, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="tanager.visualization"):
            with patch("contextily.add_basemap"):
                add_basemap(ax, source="bogus_source")
        assert any("bogus_source" in record.message for record in caplog.records)

    def test_ax_unchanged_after_network_failure(self, ax):
        """Axes xlim/ylim must remain intact when basemap fetch fails."""
        xlim_before = ax.get_xlim()
        ylim_before = ax.get_ylim()
        with patch("contextily.add_basemap", side_effect=OSError("timeout")):
            add_basemap(ax)
        assert ax.get_xlim() == xlim_before
        assert ax.get_ylim() == ylim_before


# ---------------------------------------------------------------------------
# plot_map — basemap=True integration
# ---------------------------------------------------------------------------


class TestPlotMapBasemapIntegration:
    """plot_map(basemap=True) must call add_basemap and not raise."""

    def test_basemap_true_calls_add_basemap(self, utm_da):
        with patch("tanager.visualization.add_basemap") as mock_add:
            fig = plot_map(utm_da, basemap=True)
        assert mock_add.called
        plt.close(fig)

    def test_basemap_true_returns_figure(self, utm_da):
        from matplotlib.figure import Figure
        with patch("contextily.add_basemap"):
            fig = plot_map(utm_da, basemap=True)
        assert isinstance(fig, Figure)
        plt.close(fig)

    def test_basemap_false_does_not_call_add_basemap(self, utm_da):
        with patch("tanager.visualization.add_basemap") as mock_add:
            fig = plot_map(utm_da, basemap=False)
        mock_add.assert_not_called()
        plt.close(fig)

    def test_basemap_true_network_failure_does_not_raise(self, utm_da):
        """Even if contextily fails, plot_map must return a Figure."""
        from matplotlib.figure import Figure
        with patch("contextily.add_basemap", side_effect=OSError("no network")):
            fig = plot_map(utm_da, basemap=True)
        assert isinstance(fig, Figure)
        plt.close(fig)
