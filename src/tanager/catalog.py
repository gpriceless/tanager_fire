"""STAC catalog browsing and streaming download for Tanager fire scenes.

This module connects to Planet's static STAC catalog (pystac, not pystac-client)
to discover and download Tanager-1 fire-collection imagery.  All functions are
notebook-friendly and can be called without any prior configuration.

Module-level constants
----------------------
CATALOG_URL : str  Root URL of the Planet Tanager static STAC catalog.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pystac
import requests
import requests.exceptions

logger = logging.getLogger(__name__)

CATALOG_URL: str = (
    "https://www.planet.com/data/stac/tanager-core-imagery/catalog.json"
)

# Chunk size for streaming downloads (bytes).
_DOWNLOAD_CHUNK_SIZE: int = 8192


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_catalog() -> pystac.Catalog:
    """Fetch and return the root STAC catalog.

    Returns:
        The loaded pystac.Catalog object.

    Raises:
        ConnectionError: If the catalog URL is unreachable or pystac cannot
            parse the response.
    """
    try:
        catalog = pystac.Catalog.from_file(CATALOG_URL)
        return catalog
    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"Cannot reach Tanager STAC catalog at {CATALOG_URL!r}: {exc}"
        ) from exc
    except Exception as exc:
        raise ConnectionError(
            f"Failed to load Tanager STAC catalog from {CATALOG_URL!r}: {exc}"
        ) from exc


def _parse_date(date_str: str) -> datetime:
    """Parse an ISO-8601 date string to a timezone-aware UTC datetime.

    Args:
        date_str: Date string, e.g. ``"2025-01-01"`` or ``"2025-01-01T00:00:00Z"``.

    Returns:
        A timezone-aware :class:`datetime` in UTC.
    """
    # Accept bare date (YYYY-MM-DD) or full ISO timestamp.
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(
        f"Cannot parse date string {date_str!r}. "
        "Expected ISO-8601 format, e.g. '2025-01-01' or '2025-01-01T00:00:00Z'."
    )


def _ensure_utc(dt: datetime) -> datetime:
    """Return *dt* with UTC timezone, attaching it if the datetime is naive.

    Args:
        dt: Any :class:`datetime` object (tz-aware or naive).

    Returns:
        A timezone-aware :class:`datetime` in UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_fire_scenes(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[pystac.Item]:
    """Return STAC items from the Tanager fire collection.

    Connects to the Planet static STAC catalog and traverses the ``fire``
    child catalog.  Optionally filters items by acquisition datetime.

    Args:
        start_date: Inclusive lower bound in ISO-8601 format, e.g.
            ``"2025-01-01"`` or ``"2025-01-01T00:00:00Z"``.  When ``None``
            no lower bound is applied.
        end_date: Inclusive upper bound in ISO-8601 format.  When ``None``
            no upper bound is applied.

    Returns:
        List of :class:`pystac.Item` objects, each exposing:
        - ``item.id`` — scene identifier
        - ``item.datetime`` — acquisition datetime (UTC)
        - ``item.bbox`` — bounding box ``[west, south, east, north]``
        - ``item.assets`` — dict of asset key → :class:`pystac.Asset`

    Raises:
        ConnectionError: If the catalog URL is unreachable.
        ValueError: If *start_date* or *end_date* cannot be parsed.
    """
    catalog = _load_catalog()
    fire_catalog = catalog.get_child("fire")
    if fire_catalog is None:
        logger.warning("No 'fire' child catalog found; returning empty list.")
        return []

    start_dt: Optional[datetime] = _parse_date(start_date) if start_date else None
    end_dt: Optional[datetime] = _parse_date(end_date) if end_date else None

    items: list[pystac.Item] = []
    for item in fire_catalog.get_items(recursive=True):
        if item.datetime is None:
            logger.debug("Skipping item %s: no datetime.", item.id)
            continue

        item_dt = _ensure_utc(item.datetime)

        if start_dt is not None and item_dt < start_dt:
            continue
        if end_dt is not None and item_dt > end_dt:
            continue

        items.append(item)

    logger.info("list_fire_scenes: %d item(s) matched.", len(items))
    return items


def get_scene_metadata(item: pystac.Item) -> dict:
    """Extract structured metadata from a STAC item.

    Args:
        item: A :class:`pystac.Item` as returned by :func:`list_fire_scenes`.

    Returns:
        Dictionary with the following keys:

        - ``scene_id`` (:class:`str`) — STAC item ID.
        - ``datetime`` (:class:`datetime`) — acquisition datetime (UTC).
        - ``bbox`` (:class:`list` or ``None``) — bounding box
          ``[west, south, east, north]`` in WGS-84 degrees.
        - ``product_types`` (:class:`list[str]`) — asset keys available for
          this scene (e.g. ``["analytic", "analytic_udm2"]``).
        - ``file_size_mb`` (:class:`float` or ``None``) — total size of all
          assets in megabytes, or ``None`` if size metadata is absent.
    """
    total_bytes: Optional[float] = None

    for asset in item.assets.values():
        extra = asset.extra_fields or {}
        size = extra.get("file:size") or extra.get("size")
        if size is not None:
            try:
                total_bytes = (total_bytes or 0.0) + float(size)
            except (TypeError, ValueError):
                pass

    file_size_mb: Optional[float] = (
        total_bytes / (1024 * 1024) if total_bytes is not None else None
    )

    return {
        "scene_id": item.id,
        "datetime": _ensure_utc(item.datetime) if item.datetime else None,
        "bbox": item.bbox,
        "product_types": list(item.assets.keys()),
        "file_size_mb": file_size_mb,
    }


def download_scene(
    item: pystac.Item,
    product_type: str,
    output_dir: Path,
    overwrite: bool = False,
) -> Path:
    """Stream-download a single Tanager scene asset.

    Files are written to *output_dir* using the asset's filename extracted
    from the URL.  If the file already exists and *overwrite* is ``False``,
    the download is skipped.

    Args:
        item: A :class:`pystac.Item` as returned by :func:`list_fire_scenes`.
        product_type: Asset key to download (e.g. ``"analytic"``).  Must be
            present in ``item.assets``.
        output_dir: Destination directory.  Created if it does not exist.
        overwrite: When ``False`` (default), skip download if the destination
            file already exists.

    Returns:
        :class:`pathlib.Path` of the downloaded (or already-present) file.

    Raises:
        KeyError: If *product_type* is not a key in ``item.assets``.
        ConnectionError: If the download request fails at the network level.
        requests.exceptions.HTTPError: If the server returns a non-2xx status.
    """
    if product_type not in item.assets:
        raise KeyError(
            f"Product type {product_type!r} not found in scene {item.id!r}. "
            f"Available: {list(item.assets.keys())}"
        )

    asset = item.assets[product_type]
    url: str = asset.href

    # Derive a local filename from the URL path.
    filename = url.rstrip("/").split("/")[-1] or f"{item.id}_{product_type}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / filename

    if dest.exists() and not overwrite:
        logger.info(
            "download_scene: %s already exists; skipping (overwrite=False).", dest
        )
        return dest

    logger.info("download_scene: starting download of %s -> %s", url, dest)

    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            total_mb: Optional[float] = (
                float(content_length) / (1024 * 1024)
                if content_length
                else None
            )

            downloaded_bytes = 0
            last_logged_pct = -1

            with open(dest, "wb") as fh:
                for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded_bytes += len(chunk)

                    if total_mb is not None:
                        pct = int(downloaded_bytes / float(content_length) * 100)
                        # Log every 10 % to avoid flooding the log.
                        if pct // 10 > last_logged_pct // 10:
                            logger.info(
                                "download_scene: %s — %.1f / %.1f MB (%d%%)",
                                filename,
                                downloaded_bytes / (1024 * 1024),
                                total_mb,
                                pct,
                            )
                            last_logged_pct = pct

    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"Network error downloading {url!r}: {exc}"
        ) from exc

    logger.info(
        "download_scene: completed %s (%.1f MB).",
        dest,
        downloaded_bytes / (1024 * 1024),
    )
    return dest
