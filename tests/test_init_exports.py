"""Tests for tanager.__init__ lazy exports — verifies all public API names
resolve without error and that the lazy-import caching mechanism works.

These tests do NOT import from submodules directly; they access everything
through the top-level `tanager` package to exercise __getattr__.
"""

import pytest

import tanager

# ---------------------------------------------------------------------------
# All 13 visualization names that were added in this task
# ---------------------------------------------------------------------------
VISUALIZATION_NAMES = [
    "plot_map",
    "plot_before_after",
    "plot_temporal_trajectory",
    "plot_severity_summary",
    "plot_difference_map",
    "interactive_map",
    "show_product",
    "save_figure",
    "add_basemap",
    "load_fire_perimeters",
    "overlay_perimeters",
    "add_scalebar",
    "PRODUCT_STYLES",
]

# A representative sample of pre-existing lazy exports that must not be broken
EXISTING_NAMES = [
    # config
    "SENSOR",
    "BAD_BAND_RANGES",
    "DATA_DIR",
    # catalog
    "list_fire_scenes",
    # io
    "load_scene",
    # spectral
    "select_bands",
    "nbr",
    # masks
    "nodata_mask",
    # endmembers
    "load_usgs_library",
    # unmixing
    "run_mesma",
    # severity
    "train_severity_model",
    # lfmc
    "compute_lfmc_indices",
    # validation
    "compute_accuracy",
]


class TestVisualizationLazyExports:
    """All 13 visualization names must be resolvable via tanager.<name>."""

    @pytest.mark.parametrize("name", VISUALIZATION_NAMES)
    def test_visualization_name_resolves(self, name):
        """getattr(tanager, name) must not raise AttributeError."""
        obj = getattr(tanager, name)
        assert obj is not None

    def test_all_visualization_names_resolve_together(self):
        """Batch access — same check the acceptance criteria specifies."""
        resolved = [getattr(tanager, name) for name in VISUALIZATION_NAMES]
        assert len(resolved) == 13

    def test_product_styles_is_dict(self):
        """PRODUCT_STYLES should be a dict (it's a data constant, not callable)."""
        assert isinstance(tanager.PRODUCT_STYLES, dict)


class TestExistingExportsNotBroken:
    """Pre-existing lazy exports must still resolve after the visualization
    section was added."""

    @pytest.mark.parametrize("name", EXISTING_NAMES)
    def test_existing_name_resolves(self, name):
        obj = getattr(tanager, name)
        assert obj is not None


class TestLazyImportCaching:
    """After first access, the symbol is cached in module globals so subsequent
    accesses bypass __getattr__."""

    def test_second_access_returns_same_object(self):
        first = tanager.plot_map
        second = tanager.plot_map
        assert first is second

    def test_cached_symbol_is_in_module_globals(self):
        # Access to populate the cache
        _ = tanager.save_figure
        # After access the name should be in the module's __dict__
        assert "save_figure" in vars(tanager)


class TestUnknownAttributeRaises:
    """__getattr__ must raise AttributeError for names not in _LAZY_EXPORTS."""

    def test_unknown_name_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            _ = tanager.this_does_not_exist_xyz


class TestDirIncludesVisualization:
    """dir(tanager) must include all visualization names (for IDE autocomplete)."""

    def test_dir_includes_all_visualization_names(self):
        public_names = set(dir(tanager))
        missing = [n for n in VISUALIZATION_NAMES if n not in public_names]
        assert missing == [], f"Missing from dir(tanager): {missing}"
