"""Tests for save_figure — multi-format figure export utility.

Covers: single format, multiple formats, parent directory creation,
return type, file existence, and empty formats list.
"""

import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from tanager.visualization import save_figure

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def simple_fig():
    """A minimal matplotlib Figure with one line plot."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 5, 6])
    yield fig
    plt.close(fig)


# ---------------------------------------------------------------------------
# Return type and length
# ---------------------------------------------------------------------------


class TestSaveFigureReturnType:
    def test_returns_list(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            result = save_figure(simple_fig, f"{td}/test", ["png"])
            assert isinstance(result, list)

    def test_returns_path_objects(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            result = save_figure(simple_fig, f"{td}/test", ["png"])
            assert all(isinstance(p, Path) for p in result)

    def test_single_format_returns_one_path(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            result = save_figure(simple_fig, f"{td}/test", ["png"])
            assert len(result) == 1

    def test_two_formats_returns_two_paths(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            result = save_figure(simple_fig, f"{td}/test", ["png", "pdf"])
            assert len(result) == 2

    def test_three_formats_returns_three_paths(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            result = save_figure(simple_fig, f"{td}/test", ["png", "pdf", "svg"])
            assert len(result) == 3


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


class TestSaveFigureFileExistence:
    def test_png_file_is_written(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/out", ["png"])
            assert paths[0].exists()

    def test_pdf_file_is_written(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/out", ["pdf"])
            assert paths[0].exists()

    def test_both_files_exist_for_two_formats(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/out", ["png", "pdf"])
            assert all(p.exists() for p in paths)

    def test_files_not_empty(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/out", ["png"])
            assert paths[0].stat().st_size > 0


# ---------------------------------------------------------------------------
# Path naming
# ---------------------------------------------------------------------------


class TestSaveFigurePathNaming:
    def test_png_path_has_correct_extension(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/fig", ["png"])
            assert paths[0].suffix == ".png"

    def test_pdf_path_has_correct_extension(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/fig", ["pdf"])
            assert paths[0].suffix == ".pdf"

    def test_paths_use_provided_base_name(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/my_figure", ["png"])
            assert paths[0].stem == "my_figure"

    def test_paths_order_matches_formats_order(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/fig", ["pdf", "png"])
            assert paths[0].suffix == ".pdf"
            assert paths[1].suffix == ".png"


# ---------------------------------------------------------------------------
# Parent directory creation
# ---------------------------------------------------------------------------


class TestSaveFigureParentDirectoryCreation:
    def test_creates_missing_parent_directory(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            target = f"{td}/nested/sub/fig"
            paths = save_figure(simple_fig, target, ["png"])
            assert paths[0].exists()

    def test_works_when_parent_already_exists(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            # Parent already exists — should not raise
            paths = save_figure(simple_fig, f"{td}/fig", ["png"])
            assert paths[0].exists()


# ---------------------------------------------------------------------------
# Default format
# ---------------------------------------------------------------------------


class TestSaveFigureDefaultFormat:
    def test_default_format_is_png(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/fig")
            assert len(paths) == 1
            assert paths[0].suffix == ".png"
            assert paths[0].exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestSaveFigureEdgeCases:
    def test_empty_formats_returns_empty_list(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            result = save_figure(simple_fig, f"{td}/fig", [])
            assert result == []

    def test_path_as_pathlib_path_object(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "fig"
            paths = save_figure(simple_fig, target, ["png"])
            assert paths[0].exists()

    def test_svg_format_works(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, f"{td}/fig", ["svg"])
            assert paths[0].exists()
            assert paths[0].suffix == ".svg"
