"""Tests for plot_map — geo-aware single-panel raster renderer.

Covers: UTM axes, product_name lookup, explicit overrides, NaN handling,
ax= parameter, publication mode, basemap stub, no-coords fallback, and
unknown product_name warning.
"""

import numpy as np
import pytest
import xarray as xr

# Use a non-interactive backend before any matplotlib import.
import matplotlib
matplotlib.use("Agg")

from matplotlib.figure import Figure  # noqa: E402

from tanager.visualization import PRODUCT_STYLES, plot_map  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def utm_da() -> xr.DataArray:
    """100×100 DataArray with UTM-like x/y coordinates and a NaN patch."""
    x = np.linspace(340_000, 350_000, 100)
    y = np.linspace(3_780_000, 3_790_000, 100)
    data = np.random.default_rng(0).random((100, 100))
    data[40:60, 40:60] = np.nan
    return xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])


@pytest.fixture()
def small_da() -> xr.DataArray:
    """Small 20×20 DataArray for quick edge-case tests."""
    x = np.arange(20) * 100.0 + 340_000
    y = np.arange(20) * 100.0 + 3_780_000
    data = np.random.default_rng(1).random((20, 20))
    return xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestPlotMapReturnType:
    def test_returns_figure(self, utm_da):
        fig = plot_map(utm_da)
        assert isinstance(fig, Figure)

    def test_returns_figure_with_product_name(self, utm_da):
        fig = plot_map(utm_da, product_name="nbr")
        assert isinstance(fig, Figure)


# ---------------------------------------------------------------------------
# Colorbar
# ---------------------------------------------------------------------------


class TestPlotMapColorbar:
    def test_colorbar_present(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, product_name="nbr")
        # Figure should have ≥2 axes: main plot + colorbar
        assert len(fig.get_axes()) >= 2
        plt.close(fig)

    def test_colorbar_label_from_product_styles(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, product_name="nbr")
        axes = fig.get_axes()
        # The colorbar axes ylabel is the label
        cb_ax = axes[1]
        label = cb_ax.get_ylabel()
        assert label == PRODUCT_STYLES["nbr"].label
        plt.close(fig)

    def test_colorbar_label_from_product_styles_dnbr(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, product_name="dnbr")
        cb_ax = fig.get_axes()[1]
        assert PRODUCT_STYLES["dnbr"].label in cb_ax.get_ylabel()
        plt.close(fig)


# ---------------------------------------------------------------------------
# UTM axes labels
# ---------------------------------------------------------------------------


class TestPlotMapUTMAxes:
    def test_xlabel_easting_km(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, product_name="nbr")
        ax = fig.get_axes()[0]
        assert ax.get_xlabel() == "Easting (km)"
        plt.close(fig)

    def test_ylabel_northing_km(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, product_name="nbr")
        ax = fig.get_axes()[0]
        assert ax.get_ylabel() == "Northing (km)"
        plt.close(fig)

    def test_tick_labels_formatted_in_km(self, utm_da):
        """Tick labels should show values in the hundreds-of-km range, not raw metres."""
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, product_name="nbr")
        ax = fig.get_axes()[0]
        fig.canvas.draw()
        xtick_labels = [t.get_text() for t in ax.get_xticklabels() if t.get_text()]
        # With UTM x in [340000, 350000] formatted as km → "340" … "350"
        for label in xtick_labels:
            # Labels should be small integers, not 6-digit metre values
            val = float(label)
            assert val < 10_000, f"Tick label {label!r} looks like metres, not km"
        plt.close(fig)


# ---------------------------------------------------------------------------
# ax= parameter
# ---------------------------------------------------------------------------


class TestPlotMapAxParameter:
    def test_uses_provided_ax(self, utm_da):
        import matplotlib.pyplot as plt
        fig_pre, ax_pre = plt.subplots()
        result_fig = plot_map(utm_da, ax=ax_pre)
        assert result_fig is fig_pre
        plt.close("all")

    def test_creates_new_figure_when_ax_is_none(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da)
        assert isinstance(fig, Figure)
        plt.close(fig)


# ---------------------------------------------------------------------------
# NaN handling
# ---------------------------------------------------------------------------


class TestPlotMapNaNHandling:
    def test_all_nan_does_not_raise(self, small_da):
        import matplotlib.pyplot as plt
        all_nan = small_da.copy(data=np.full(small_da.shape, np.nan))
        fig = plot_map(all_nan, product_name="nbr")
        assert isinstance(fig, Figure)
        plt.close(fig)

    def test_partial_nan_does_not_raise(self, utm_da):
        import matplotlib.pyplot as plt
        # utm_da already has NaN patch
        fig = plot_map(utm_da, product_name="nbr")
        assert isinstance(fig, Figure)
        plt.close(fig)


# ---------------------------------------------------------------------------
# product_name style lookup
# ---------------------------------------------------------------------------


class TestPlotMapProductNameLookup:
    @pytest.mark.parametrize("product", sorted(PRODUCT_STYLES.keys()))
    def test_all_known_products_work(self, small_da, product):
        import matplotlib.pyplot as plt
        fig = plot_map(small_da, product_name=product)
        assert isinstance(fig, Figure)
        plt.close(fig)

    def test_unknown_product_name_logs_warning_and_returns_figure(self, utm_da, caplog):
        import logging
        import matplotlib.pyplot as plt
        with caplog.at_level(logging.WARNING, logger="tanager.visualization"):
            fig = plot_map(utm_da, product_name="bogus_product_xyz")
        assert isinstance(fig, Figure)
        assert "bogus_product_xyz" in caplog.text
        plt.close(fig)


# ---------------------------------------------------------------------------
# Explicit parameter overrides
# ---------------------------------------------------------------------------


class TestPlotMapExplicitOverrides:
    def test_explicit_cmap_overrides_product_style(self, small_da):
        """Explicit cmap should be used even if product_name provides one."""
        import matplotlib.pyplot as plt
        # This should not raise — explicit cmap wins
        fig = plot_map(small_da, product_name="nbr", cmap="plasma")
        assert isinstance(fig, Figure)
        plt.close(fig)

    def test_explicit_vmin_vmax_override_product_style(self, small_da):
        import matplotlib.pyplot as plt
        fig = plot_map(small_da, product_name="nbr", vmin=0.0, vmax=0.5)
        assert isinstance(fig, Figure)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Publication mode
# ---------------------------------------------------------------------------


class TestPlotMapPublicationMode:
    def test_publication_sets_dpi_300(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, publication=True)
        assert fig.get_dpi() == 300
        plt.close(fig)

    def test_non_publication_does_not_set_dpi_300(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, publication=False)
        # Default dpi is typically 100; should NOT be forced to 300
        assert fig.get_dpi() != 300
        plt.close(fig)


# ---------------------------------------------------------------------------
# Basemap (stub) — graceful fallback
# ---------------------------------------------------------------------------


class TestPlotMapBasemap:
    def test_basemap_true_does_not_raise(self, utm_da):
        import matplotlib.pyplot as plt
        # add_basemap raises NotImplementedError; plot_map should swallow it
        fig = plot_map(utm_da, basemap=True)
        assert isinstance(fig, Figure)
        plt.close(fig)


# ---------------------------------------------------------------------------
# No-coordinate DataArray fallback
# ---------------------------------------------------------------------------


class TestPlotMapNoCoords:
    def test_no_coords_does_not_raise(self):
        import matplotlib.pyplot as plt
        da = xr.DataArray(np.random.default_rng(42).random((30, 30)))
        fig = plot_map(da, title="No coords")
        assert isinstance(fig, Figure)
        plt.close(fig)

    def test_no_coords_no_utm_axis_labels(self):
        import matplotlib.pyplot as plt
        da = xr.DataArray(np.random.default_rng(43).random((30, 30)))
        fig = plot_map(da)
        ax = fig.get_axes()[0]
        # Without geo coords, no Easting/Northing labels applied
        assert ax.get_xlabel() == ""
        assert ax.get_ylabel() == ""
        plt.close(fig)


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------


class TestPlotMapTitle:
    def test_title_is_set(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, title="My Map Title")
        ax = fig.get_axes()[0]
        assert ax.get_title() == "My Map Title"
        plt.close(fig)

    def test_empty_title_not_set(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, title="")
        ax = fig.get_axes()[0]
        assert ax.get_title() == ""
        plt.close(fig)


# ---------------------------------------------------------------------------
# figsize
# ---------------------------------------------------------------------------


class TestPlotMapFigsize:
    def test_custom_figsize(self, utm_da):
        import matplotlib.pyplot as plt
        fig = plot_map(utm_da, figsize=(6, 4))
        w, h = fig.get_size_inches()
        assert abs(w - 6) < 0.01
        assert abs(h - 4) < 0.01
        plt.close(fig)
