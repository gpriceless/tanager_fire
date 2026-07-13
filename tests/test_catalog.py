"""Tests for tanager.catalog — STAC catalog browsing and download.

All external network calls are mocked.  Tests verify behaviour, not
implementation internals.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pystac
import pytest
import requests

from tanager.catalog import (
    CATALOG_URL,
    _ensure_utc,
    _parse_date,
    download_scene,
    get_scene_metadata,
    list_fire_scenes,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_item(
    item_id: str = "scene_001",
    dt: datetime | None = None,
    bbox: list | None = None,
    assets: dict | None = None,
) -> pystac.Item:
    """Build a minimal pystac.Item for testing."""
    if dt is None:
        dt = datetime(2025, 1, 23, 18, 55, 0, tzinfo=timezone.utc)
    if bbox is None:
        bbox = [-118.5, 34.0, -118.0, 34.5]
    if assets is None:
        assets = {
            "analytic": pystac.Asset(href="https://example.com/scene_001_analytic.h5"),
        }
    item = pystac.Item(
        id=item_id,
        geometry=None,
        bbox=bbox,
        datetime=dt,
        properties={},
    )
    item.assets = assets
    return item


def _make_fire_catalog(items: list[pystac.Item]) -> pystac.Catalog:
    """Build a minimal fire sub-catalog containing *items*."""
    fire_cat = pystac.Catalog(id="fire", description="fire")
    for item in items:
        fire_cat.add_item(item)
    root = pystac.Catalog(id="root", description="root")
    root.add_child(fire_cat)
    return root


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_full_iso_timestamp(self):
        dt = _parse_date("2025-01-23T18:55:07Z")
        assert dt == datetime(2025, 1, 23, 18, 55, 7, tzinfo=timezone.utc)

    def test_bare_date(self):
        dt = _parse_date("2025-01-01")
        assert dt == datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot parse date string"):
            _parse_date("not-a-date")


# ---------------------------------------------------------------------------
# _ensure_utc
# ---------------------------------------------------------------------------


class TestEnsureUtc:
    def test_naive_gets_utc(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)
        result = _ensure_utc(naive)
        assert result.tzinfo is timezone.utc

    def test_already_utc_unchanged(self):
        aware = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _ensure_utc(aware)
        assert result == aware


# ---------------------------------------------------------------------------
# list_fire_scenes
# ---------------------------------------------------------------------------


class TestListFireScenes:
    def _patch_catalog(self, root_catalog: pystac.Catalog):
        return patch(
            "tanager.catalog.pystac.Catalog.from_file",
            return_value=root_catalog,
        )

    def test_returns_all_items_when_no_filter(self):
        items = [_make_item(f"scene_{i:03d}") for i in range(5)]
        root = _make_fire_catalog(items)
        with self._patch_catalog(root):
            result = list_fire_scenes()
        assert len(result) == 5

    def test_filters_by_start_date(self):
        items = [
            _make_item("early", dt=datetime(2024, 12, 15, tzinfo=timezone.utc)),
            _make_item("late", dt=datetime(2025, 1, 23, tzinfo=timezone.utc)),
        ]
        root = _make_fire_catalog(items)
        with self._patch_catalog(root):
            result = list_fire_scenes(start_date="2025-01-01")
        assert len(result) == 1
        assert result[0].id == "late"

    def test_filters_by_end_date(self):
        items = [
            _make_item("early", dt=datetime(2024, 12, 15, tzinfo=timezone.utc)),
            _make_item("late", dt=datetime(2025, 1, 23, tzinfo=timezone.utc)),
        ]
        root = _make_fire_catalog(items)
        with self._patch_catalog(root):
            result = list_fire_scenes(end_date="2024-12-31")
        assert len(result) == 1
        assert result[0].id == "early"

    def test_filters_by_date_range(self):
        items = [
            _make_item("before", dt=datetime(2024, 11, 1, tzinfo=timezone.utc)),
            _make_item("inside", dt=datetime(2024, 12, 15, tzinfo=timezone.utc)),
            _make_item("after", dt=datetime(2025, 2, 1, tzinfo=timezone.utc)),
        ]
        root = _make_fire_catalog(items)
        with self._patch_catalog(root):
            result = list_fire_scenes(start_date="2024-12-01", end_date="2025-01-01")
        assert len(result) == 1
        assert result[0].id == "inside"

    def test_empty_fire_catalog_returns_empty_list(self):
        root = _make_fire_catalog([])
        with self._patch_catalog(root):
            result = list_fire_scenes()
        assert result == []

    def test_missing_fire_child_returns_empty_list(self):
        root = pystac.Catalog(id="root", description="root")
        with self._patch_catalog(root):
            result = list_fire_scenes()
        assert result == []

    def test_connection_error_on_network_failure(self):
        with patch(
            "tanager.catalog.pystac.Catalog.from_file",
            side_effect=requests.exceptions.ConnectionError("timeout"),
        ):
            with pytest.raises(ConnectionError, match=CATALOG_URL):
                list_fire_scenes()

    def test_connection_error_on_pystac_failure(self):
        with patch(
            "tanager.catalog.pystac.Catalog.from_file",
            side_effect=Exception("bad json"),
        ):
            with pytest.raises(ConnectionError, match=CATALOG_URL):
                list_fire_scenes()

    def test_items_with_no_datetime_skipped(self, caplog):
        # pystac requires start_datetime+end_datetime when datetime is None.
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        item_no_dt = pystac.Item(
            id="nodatetime",
            geometry=None,
            bbox=[-118.5, 34.0, -118.0, 34.5],
            datetime=None,
            properties={},
            start_datetime=start,
            end_datetime=end,
        )
        # Patch item.datetime to None after construction to simulate the
        # catalog code path where an item has no datetime field.
        item_no_dt.datetime = None

        item_ok = _make_item("has_dt")
        root = _make_fire_catalog([item_no_dt, item_ok])
        with self._patch_catalog(root):
            with caplog.at_level(logging.DEBUG, logger="tanager.catalog"):
                result = list_fire_scenes()
        assert len(result) == 1
        assert result[0].id == "has_dt"

    def test_tz_naive_item_datetime_handled(self):
        naive_dt_item = _make_item(
            "naive_scene",
            dt=datetime(2025, 1, 23, 18, 55, 0),  # no tzinfo
        )
        root = _make_fire_catalog([naive_dt_item])
        with self._patch_catalog(root):
            result = list_fire_scenes(start_date="2025-01-01")
        assert len(result) == 1

    def test_invalid_start_date_raises_value_error(self):
        root = _make_fire_catalog([])
        with self._patch_catalog(root):
            with pytest.raises(ValueError, match="Cannot parse date string"):
                list_fire_scenes(start_date="bad-date")


# ---------------------------------------------------------------------------
# get_scene_metadata
# ---------------------------------------------------------------------------


class TestGetSceneMetadata:
    def test_basic_fields_present(self):
        item = _make_item()
        meta = get_scene_metadata(item)
        assert meta["scene_id"] == "scene_001"
        assert isinstance(meta["datetime"], datetime)
        assert meta["bbox"] == [-118.5, 34.0, -118.0, 34.5]
        assert meta["product_types"] == ["analytic"]

    def test_file_size_mb_none_when_absent(self):
        item = _make_item()
        meta = get_scene_metadata(item)
        assert meta["file_size_mb"] is None

    def test_file_size_mb_computed_from_extra_fields(self):
        asset = pystac.Asset(
            href="https://example.com/scene.h5",
            extra_fields={"file:size": 512 * 1024 * 1024},  # 512 MB in bytes
        )
        item = _make_item(assets={"analytic": asset})
        meta = get_scene_metadata(item)
        assert meta["file_size_mb"] == pytest.approx(512.0)

    def test_multiple_assets_file_size_summed(self):
        assets = {
            "analytic": pystac.Asset(
                href="https://example.com/a.h5",
                extra_fields={"file:size": 256 * 1024 * 1024},
            ),
            "udm2": pystac.Asset(
                href="https://example.com/b.h5",
                extra_fields={"file:size": 10 * 1024 * 1024},
            ),
        }
        item = _make_item(assets=assets)
        meta = get_scene_metadata(item)
        assert meta["file_size_mb"] == pytest.approx(266.0)

    def test_product_types_lists_all_asset_keys(self):
        assets = {
            "analytic": pystac.Asset(href="https://example.com/a.h5"),
            "udm2": pystac.Asset(href="https://example.com/b.tif"),
            "thumbnail": pystac.Asset(href="https://example.com/thumb.jpg"),
        }
        item = _make_item(assets=assets)
        meta = get_scene_metadata(item)
        assert set(meta["product_types"]) == {"analytic", "udm2", "thumbnail"}

    def test_no_datetime_item_returns_none(self):
        # pystac requires start+end when datetime is None; patch after creation.
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        item = pystac.Item(
            id="nodatetime",
            geometry=None,
            bbox=[-118.5, 34.0, -118.0, 34.5],
            datetime=None,
            properties={},
            start_datetime=start,
            end_datetime=end,
        )
        item.datetime = None
        item.assets = {}
        meta = get_scene_metadata(item)
        assert meta["datetime"] is None

    def test_datetime_is_utc_aware(self):
        item = _make_item()
        meta = get_scene_metadata(item)
        assert meta["datetime"].tzinfo is not None


# ---------------------------------------------------------------------------
# download_scene
# ---------------------------------------------------------------------------


class TestDownloadScene:
    def _make_response(
        self,
        content: bytes = b"fakecontent",
        status_code: int = 200,
        content_length: str | None = None,
    ) -> MagicMock:
        """Build a mock requests.Response suitable for streaming."""
        response = MagicMock()
        response.status_code = status_code
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                f"{status_code} Error"
            )
        # iter_content yields the content in one chunk for simplicity
        response.iter_content.return_value = [content]
        headers = {}
        if content_length is not None:
            headers["Content-Length"] = content_length
        response.headers = headers
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    def test_downloads_file_to_output_dir(self, tmp_path):
        item = _make_item()
        response = self._make_response(b"binarydata")

        with patch("tanager.catalog.requests.get", return_value=response):
            result = download_scene(item, "analytic", tmp_path)

        assert result.exists()
        assert result.read_bytes() == b"binarydata"

    def test_returns_path_object(self, tmp_path):
        item = _make_item()
        response = self._make_response(b"x")

        with patch("tanager.catalog.requests.get", return_value=response):
            result = download_scene(item, "analytic", tmp_path)

        assert isinstance(result, Path)

    def test_skip_existing_when_overwrite_false(self, tmp_path):
        item = _make_item()
        dest = tmp_path / "scene_001_analytic.h5"
        dest.write_bytes(b"existing")

        with patch("tanager.catalog.requests.get") as mock_get:
            result = download_scene(item, "analytic", tmp_path, overwrite=False)

        mock_get.assert_not_called()
        assert result == dest

    def test_overwrites_when_overwrite_true(self, tmp_path):
        item = _make_item()
        dest = tmp_path / "scene_001_analytic.h5"
        dest.write_bytes(b"old")
        response = self._make_response(b"new")

        with patch("tanager.catalog.requests.get", return_value=response):
            download_scene(item, "analytic", tmp_path, overwrite=True)

        assert dest.read_bytes() == b"new"

    def test_creates_output_dir_if_missing(self, tmp_path):
        item = _make_item()
        new_dir = tmp_path / "new" / "nested"
        response = self._make_response(b"data")

        with patch("tanager.catalog.requests.get", return_value=response):
            result = download_scene(item, "analytic", new_dir)

        assert new_dir.exists()
        assert result.exists()

    def test_invalid_product_type_raises_key_error(self, tmp_path):
        item = _make_item()
        with pytest.raises(KeyError, match="nonexistent"):
            download_scene(item, "nonexistent", tmp_path)

    def test_connection_error_wraps_as_connection_error(self, tmp_path):
        item = _make_item()

        with patch(
            "tanager.catalog.requests.get",
            side_effect=requests.exceptions.ConnectionError("no route"),
        ):
            with pytest.raises(ConnectionError, match="Network error downloading"):
                download_scene(item, "analytic", tmp_path)

    def test_http_error_propagates(self, tmp_path):
        item = _make_item()
        response = self._make_response(b"", status_code=404)

        with patch("tanager.catalog.requests.get", return_value=response):
            with pytest.raises(requests.exceptions.HTTPError):
                download_scene(item, "analytic", tmp_path)

    def test_progress_logging_with_content_length(self, tmp_path, caplog):
        item = _make_item()
        content = b"x" * (10 * 1024 * 1024)  # 10 MB
        response = self._make_response(
            content, content_length=str(len(content))
        )

        with patch("tanager.catalog.requests.get", return_value=response):
            with caplog.at_level(logging.INFO, logger="tanager.catalog"):
                download_scene(item, "analytic", tmp_path)

        # At least one progress log line should mention %
        progress_lines = [r for r in caplog.records if "%" in r.message]
        assert len(progress_lines) >= 1

    def test_filename_derived_from_url(self, tmp_path):
        asset = pystac.Asset(
            href="https://example.com/tanager-scene-custom-name.h5"
        )
        item = _make_item(assets={"analytic": asset})
        response = self._make_response(b"data")

        with patch("tanager.catalog.requests.get", return_value=response):
            result = download_scene(item, "analytic", tmp_path)

        assert result.name == "tanager-scene-custom-name.h5"
