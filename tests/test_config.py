"""Tests for tanager.config — sensor constants, bad-band integrity, and the
``parallel_jobs()`` joblib worker cap (LGT-1012 / TD-13).

``parallel_jobs()`` is safety-critical: it bounds joblib worker counts so that
concurrent notebook/pipeline runs cannot OOM the machine. These tests pin its
env-var contract (``TANAGER_MAX_JOBS``) and the integrity of the module-level
constants used throughout the pipeline.

No heavy dependencies are required — tanager.config must stay stdlib-only.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from tanager.config import (
    BAD_BAND_RANGES,
    BAND_ALIASES,
    DATA_DIR,
    DEFAULT_MAX_JOBS,
    FIRE_SCENES,
    SENSOR,
    parallel_jobs,
)

ENV_VAR = "TANAGER_MAX_JOBS"


# ---------------------------------------------------------------------------
# parallel_jobs() — env var contract
# ---------------------------------------------------------------------------


class TestParallelJobs:
    def test_unset_returns_default(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert parallel_jobs() == DEFAULT_MAX_JOBS

    def test_unset_honours_custom_default(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert parallel_jobs(default=2) == 2

    def test_valid_positive_int(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "8")
        assert parallel_jobs() == 8

    def test_positive_int_with_whitespace(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "  6  ")
        assert parallel_jobs() == 6

    @pytest.mark.parametrize("raw", ["-1", "-5", "-100"])
    def test_negative_means_all_cores(self, raw, monkeypatch):
        """Any negative value is the explicit opt-in to unbounded n_jobs=-1."""
        monkeypatch.setenv(ENV_VAR, raw)
        assert parallel_jobs() == -1

    def test_zero_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "0")
        assert parallel_jobs() == DEFAULT_MAX_JOBS

    @pytest.mark.parametrize("raw", ["abc", "4.5", "four", "1e2", "--2", ""])
    def test_invalid_values_fall_back_to_default(self, raw, monkeypatch):
        monkeypatch.setenv(ENV_VAR, raw)
        assert parallel_jobs() == DEFAULT_MAX_JOBS

    def test_whitespace_only_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "   ")
        assert parallel_jobs() == DEFAULT_MAX_JOBS

    def test_invalid_value_honours_custom_default(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "not-a-number")
        assert parallel_jobs(default=3) == 3

    def test_default_max_jobs_is_bounded(self):
        """The module default must be a small positive cap, never unbounded."""
        assert isinstance(DEFAULT_MAX_JOBS, int)
        assert 1 <= DEFAULT_MAX_JOBS <= 8


# ---------------------------------------------------------------------------
# SENSOR constants
# ---------------------------------------------------------------------------


class TestSensor:
    def test_identity_and_band_count(self):
        assert SENSOR.name == "Tanager-1"
        assert SENSOR.n_bands == 426

    def test_spectral_range(self):
        assert SENSOR.wavelength_min_nm == 380
        assert SENSOR.wavelength_max_nm == 2500
        assert SENSOR.wavelength_min_nm < SENSOR.wavelength_max_nm

    def test_resolutions(self):
        assert SENSOR.spectral_resolution_nm > 0
        assert SENSOR.spatial_resolution_m == 30
        assert SENSOR.swath_width_km == 18


# ---------------------------------------------------------------------------
# BAD_BAND_RANGES integrity
# ---------------------------------------------------------------------------


class TestBadBandRanges:
    def test_shape(self):
        assert isinstance(BAD_BAND_RANGES, list)
        assert len(BAD_BAND_RANGES) > 0
        for entry in BAD_BAND_RANGES:
            assert isinstance(entry, tuple)
            assert len(entry) == 2

    def test_each_range_is_ordered(self):
        for low, high in BAD_BAND_RANGES:
            assert low < high, f"range ({low}, {high}) is not ascending"

    def test_ranges_within_sensor_limits(self):
        for low, high in BAD_BAND_RANGES:
            assert low >= 0
            assert high <= SENSOR.wavelength_max_nm

    def test_ranges_sorted_and_non_overlapping(self):
        for (_, prev_high), (next_low, _) in zip(
            BAD_BAND_RANGES, BAD_BAND_RANGES[1:]
        ):
            assert prev_high < next_low, "bad-band ranges overlap or are unsorted"

    def test_known_water_vapour_bands_are_covered(self):
        """Sensor-flagged water vapour absorption bands must stay excluded."""

        def covered(nm: float) -> bool:
            return any(low <= nm <= high for low, high in BAD_BAND_RANGES)

        assert covered(1400)  # water vapour band 1 (1342–1438 nm flagged)
        assert covered(1900)  # water vapour band 2 (1783–1967 nm flagged)
        assert covered(2450)  # long-wave sensor edge


# ---------------------------------------------------------------------------
# BAND_ALIASES integrity
# ---------------------------------------------------------------------------


class TestBandAliases:
    EXPECTED_NAMES = {"BLUE", "GREEN", "RED", "RED_EDGE", "NIR", "SWIR1", "SWIR2"}

    def test_expected_aliases_present(self):
        assert set(BAND_ALIASES) == self.EXPECTED_NAMES

    def test_alias_wavelengths_within_sensor_range(self):
        for name, nm in BAND_ALIASES.items():
            assert SENSOR.wavelength_min_nm <= nm <= SENSOR.wavelength_max_nm, name

    def test_no_alias_falls_in_a_bad_band(self):
        for name, nm in BAND_ALIASES.items():
            for low, high in BAD_BAND_RANGES:
                assert not (low <= nm <= high), (
                    f"{name} ({nm} nm) falls inside bad band ({low}, {high})"
                )


# ---------------------------------------------------------------------------
# FIRE_SCENES catalog integrity
# ---------------------------------------------------------------------------


class TestFireScenes:
    VALID_PHASES = {
        "pre-fire",
        "post-fire",
        "early-recovery",
        "mid-recovery",
        "late-recovery",
        "other",
    }

    def test_scene_count_matches_research(self):
        # 11 scenes confirmed in the static STAC catalog (2026-04-27 research).
        assert len(FIRE_SCENES) == 11

    def test_required_keys_and_types(self):
        required = {"datetime", "phase", "days_relative_to_ignition", "notes", "bbox"}
        for scene_id, meta in FIRE_SCENES.items():
            assert required <= set(meta), f"{scene_id} missing keys"
            assert meta["phase"] in self.VALID_PHASES, scene_id
            days = meta["days_relative_to_ignition"]
            assert days is None or isinstance(days, int), scene_id

    def test_datetimes_parse_and_match_scene_ids(self):
        for scene_id, meta in FIRE_SCENES.items():
            dt = datetime.strptime(meta["datetime"], "%Y-%m-%dT%H:%M:%SZ")
            assert scene_id.startswith(dt.strftime("%Y%m%d")), scene_id

    def test_off_footprint_scenes_have_no_relative_days(self):
        for scene_id, meta in FIRE_SCENES.items():
            if meta["phase"] == "other":
                assert meta["days_relative_to_ignition"] is None, scene_id
            else:
                assert isinstance(meta["days_relative_to_ignition"], int), scene_id


# ---------------------------------------------------------------------------
# DATA_DIR and import purity
# ---------------------------------------------------------------------------


class TestModuleBasics:
    def test_data_dir_is_a_path(self):
        assert isinstance(DATA_DIR, Path)

    def test_config_import_is_stdlib_only(self):
        """tanager.config must be importable without heavy optional deps.

        Run in a subprocess so this session's already-imported modules don't
        mask a regression that adds a heavy import to config.py.
        """
        code = (
            "import sys\n"
            "import tanager.config\n"
            "heavy = {'rasterio', 'xarray', 'hypercoast', 'spectral', 'geopandas'}\n"
            "loaded = heavy & set(sys.modules)\n"
            "assert not loaded, f'config import pulled in heavy deps: {loaded}'\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert result.returncode == 0, result.stderr
