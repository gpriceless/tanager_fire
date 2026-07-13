"""Unit tests for show_product convenience helper.

Covers:
- Static path (interactive=False): returns matplotlib Figure with basemap
- Title composition: product_name.upper() + scene_date
- product_name auto-detection from da.name
- scene_date is optional (defaults to empty string in title)
- interactive path delegates to interactive_map
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest
import rioxarray  # noqa: F401 — registers .rio accessor
import xarray as xr

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def georef_da() -> xr.DataArray:
    """Synthetic 50×50 DataArray with EPSG:32611 CRS."""
    x = np.linspace(340_000, 350_000, 50)
    y = np.linspace(3_780_000, 3_790_000, 50)
    rng = np.random.default_rng(42)
    da = xr.DataArray(rng.random((50, 50)), coords={"y": y, "x": x}, dims=["y", "x"])
    return da.rio.write_crs("EPSG:32611")


# ---------------------------------------------------------------------------
# Static path: returns matplotlib Figure
# ---------------------------------------------------------------------------


class TestShowProductReturnsFigure:
    """show_product(interactive=False) must return a matplotlib Figure."""

    def test_returns_matplotlib_figure(self, georef_da):
        from matplotlib.figure import Figure

        from tanager.visualization import show_product

        fig = show_product(georef_da, "nbr", "2025-01-23")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)

    def test_has_axes_attribute(self, georef_da):
        from tanager.visualization import show_product

        fig = show_product(georef_da, "nbr", "2025-01-23")
        try:
            assert hasattr(fig, "axes")
        finally:
            plt.close(fig)

    def test_figure_has_at_least_one_axes(self, georef_da):
        from tanager.visualization import show_product

        fig = show_product(georef_da, "nbr")
        try:
            assert len(fig.axes) >= 1
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# Title composition
# ---------------------------------------------------------------------------


class TestShowProductTitle:
    """Title must be '{product_name.upper()} {scene_date}' when both are provided."""

    def test_title_contains_product_name_uppercased(self, georef_da):
        from tanager.visualization import show_product

        fig = show_product(georef_da, "nbr", "2025-01-23")
        try:
            ax = fig.axes[0]
            assert "NBR" in ax.get_title(), (
                f"Expected 'NBR' in title, got {ax.get_title()!r}"
            )
        finally:
            plt.close(fig)

    def test_title_contains_scene_date(self, georef_da):
        from tanager.visualization import show_product

        fig = show_product(georef_da, "nbr", "2025-01-23")
        try:
            ax = fig.axes[0]
            assert "2025-01-23" in ax.get_title(), (
                f"Expected '2025-01-23' in title, got {ax.get_title()!r}"
            )
        finally:
            plt.close(fig)

    def test_title_without_scene_date_has_no_trailing_space(self, georef_da):
        """When scene_date is None, the title must not have a trailing space."""
        from tanager.visualization import show_product

        fig = show_product(georef_da, "nbr")
        try:
            ax = fig.axes[0]
            title = ax.get_title()
            assert not title.endswith(" "), (
                f"Title should not have trailing space when scene_date=None, got {title!r}"
            )
        finally:
            plt.close(fig)

    def test_title_with_dnbr_product(self, georef_da):
        from tanager.visualization import show_product

        fig = show_product(georef_da, "dnbr", "2024-12-31")
        try:
            title = fig.axes[0].get_title()
            assert "DNBR" in title
            assert "2024-12-31" in title
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# Auto-detect product_name from da.name
# ---------------------------------------------------------------------------


class TestShowProductAutoDetect:
    """When product_name is not given, da.name should be used."""

    def test_auto_detect_product_from_da_name(self, georef_da):
        from tanager.visualization import show_product

        named_da = georef_da.copy()
        named_da.name = "ndvi"

        fig = show_product(named_da, scene_date="2025-01-07")
        try:
            title = fig.axes[0].get_title()
            assert "NDVI" in title, (
                f"Expected 'NDVI' in title when da.name='ndvi', got {title!r}"
            )
        finally:
            plt.close(fig)

    def test_explicit_product_name_overrides_da_name(self, georef_da):
        from tanager.visualization import show_product

        named_da = georef_da.copy()
        named_da.name = "ndvi"  # should be ignored

        fig = show_product(named_da, product_name="nbr")
        try:
            title = fig.axes[0].get_title()
            assert "NBR" in title, (
                f"Expected 'NBR' (explicit override), got {title!r}"
            )
        finally:
            plt.close(fig)

    def test_no_product_name_and_no_da_name_renders(self, georef_da):
        """Passing neither product_name nor da.name must still render without error."""
        from matplotlib.figure import Figure

        from tanager.visualization import show_product

        fig = show_product(georef_da)
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# interactive=True delegates to interactive_map
# ---------------------------------------------------------------------------


class TestShowProductInteractive:
    """interactive=True must delegate to interactive_map and return a Map widget."""

    def test_interactive_calls_interactive_map(self, georef_da):
        """interactive_map must be called when interactive=True."""
        from unittest.mock import MagicMock, patch

        from tanager.visualization import show_product

        mock_map = MagicMock()
        with patch("tanager.visualization.interactive_map", return_value=mock_map) as mock_fn:
            result = show_product(georef_da, "nbr", interactive=True)

        mock_fn.assert_called_once()
        assert result is mock_map

    def test_interactive_passes_da_and_product_name(self, georef_da):
        """The layers list [(da, product_name)] must be forwarded to interactive_map."""
        from unittest.mock import MagicMock, patch

        from tanager.visualization import show_product

        mock_map = MagicMock()
        with patch("tanager.visualization.interactive_map", return_value=mock_map) as mock_fn:
            show_product(georef_da, "nbr", interactive=True)

        call_args = mock_fn.call_args
        # First positional arg is the layers list
        layers = call_args[0][0]
        assert len(layers) == 1
        da_arg, name_arg = layers[0]
        assert da_arg is georef_da
        assert name_arg == "nbr"

    def test_static_does_not_call_interactive_map(self, georef_da):
        """When interactive=False, interactive_map must not be called."""
        from unittest.mock import patch

        from tanager.visualization import show_product

        with patch("tanager.visualization.interactive_map") as mock_fn:
            fig = show_product(georef_da, "nbr", interactive=False)

        mock_fn.assert_not_called()
        plt.close(fig)


# ---------------------------------------------------------------------------
# Basemap behaviour
# ---------------------------------------------------------------------------


class TestShowProductBasemap:
    """Static show_product must call add_basemap (via plot_map basemap=True)."""

    def test_basemap_called_on_static(self, georef_da):
        """contextily.add_basemap must be invoked for the static render path."""
        from unittest.mock import patch

        from tanager.visualization import show_product

        with patch("contextily.add_basemap") as mock_ctx:
            fig = show_product(georef_da, "nbr", "2025-01-23")

        try:
            assert mock_ctx.called, "Expected contextily.add_basemap to be called"
        finally:
            plt.close(fig)
