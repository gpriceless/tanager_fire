# BAER Soil Burn Severity — Hughes fire

`hughes_sbs.tif` is the independent ground truth behind notebook 02's only accuracy
claim (Cohen's kappa 0.527 against single-date Tanager NBR). It is committed via a
`.gitignore` exception (`!data/reference/baer/*.tif`) because at 198 KB it is small
enough to bundle, and without it that validation cannot be reproduced from a clone.

| | |
|---|---|
| Size | 197,801 bytes |
| MD5 | `910f02a999989bc63bde846b2f06e489` |
| Grid | 483 × 330, 25.2978 m pixels |
| CRS | EPSG:32611 (UTM 11N) |
| Bounds | 350557.6, 3815750.4 → 358905.9, 3827969.2 |

## Provenance

**Not recorded, and not recoverable from the file.** It carries no colormap, no band
description, and no metadata tags beyond `DataType=Generic` / `AREA_OR_POINT=Area`.

BAER Soil Burn Severity products for US fires are published by the interagency
Burned Area Emergency Response program via <https://burnseverity.cr.usgs.gov/baer/>,
which is where a replacement should be obtained. As a work of the US federal
government, such a product is generally not subject to copyright (17 U.S.C. § 105).
This file has not been checksum-matched against a specific published product — if you
re-download it, verify the class coding below still holds before trusting it.

## Class coding — verify before use

**Do not assume the codes.** BAER SBS encodings vary between products, and this
raster's coding is *not* what `tanager.validation.SBS_CODE_MAP` assumes. Passing that
default map here now raises (`load_barc_reference(..., strict=True)`, the default)
because it has no entry for code 15 — which is 81,297 px, the largest region in the
file. That guard exists because an earlier analysis mislabelled these classes and
reported a kappa that could not be reproduced.

The coding below was established by inspecting the raster's spatial structure and the
per-class Tanager NBR/NDVI, not from documentation:

| Code | Pixels | Median NBR | Median NDVI | Meaning | Evidence |
|---|---|---|---|---|---|
| 0 | 12,450 | +0.050 | +0.301 | **Outside mapped extent** (nodata) | One connected component; touches every raster edge; the only code present on the border. BAER never assessed it. |
| 15 | 81,297 | +0.025 | +0.273 | **Unburned / very low**, inside perimeter | 16 interior components, touching no edge; spectrally indistinguishable from the unmapped surroundings. |
| 1 | 6,099 | −0.216 | +0.160 | Low | Fragmented (828 components), typical of per-pixel severity. |
| 2 | 34,878 | −0.375 | +0.130 | Moderate-Low | |
| 3 | 24,525 | −0.415 | +0.104 | Moderate-High | |
| 4 | 141 | −0.355 | +0.114 | High | Too few pixels to calibrate, and *brighter* than code 3 — single-date NBR cannot order it. Merge into 3. |

Pixel counts are raw raster counts; the NBR/NDVI medians are over pixels co-located
with the Tanager scene `20250123_185507_64_4001` (swath 1, Hughes) after masking.

The map notebook 02 uses, which satisfies `strict=True` (all six codes covered):

```python
HUGHES_SBS_CODE_MAP = {0: -1, 15: 0, 1: 1, 2: 2, 3: 3, 4: 3}
```

## Why this scene

Tanager imaged the Hughes fire in swath 1 of the 2025-01-23 overpass
(`20250123_185507_64_4001`), eleven seconds before the Palisades swath used for the
notebook's severity product — same sensor, day, illumination and atmosphere. Tanager
has **no pre-fire scene** over the Hughes footprint, so the validation uses
single-date post-fire NBR rather than dNBR. See notebook 02 Section 7.
