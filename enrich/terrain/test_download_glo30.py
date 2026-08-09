"""Tile arithmetic for the GLO-30 downloader — pure, no network."""
from download_glo30 import tile_name, tile_url, tiles_for_bbox


def test_tiles_for_bbox_spans_tile_rows():
    assert tiles_for_bbox(14.2, 49.9, 14.7, 50.2) == [(49, 14), (50, 14)]


def test_tiles_for_bbox_exact_edges_are_exclusive():
    assert tiles_for_bbox(14.0, 49.0, 15.0, 50.0) == [(49, 14)]


def test_tiles_for_bbox_degenerate_point_still_yields_its_tile():
    assert tiles_for_bbox(14.0, 49.0, 14.0, 49.0) == [(49, 14)]


def test_default_cz_bbox_tile_count():
    tiles = tiles_for_bbox(11.5, 47.5, 19.5, 51.5)
    assert len(tiles) == 5 * 9
    assert (50, 14) in tiles and (47, 11) in tiles and (51, 19) in tiles


def test_tile_name_hemispheres_and_zero_padding():
    assert tile_name(50, 14) == "Copernicus_DSM_COG_10_N50_00_E014_00_DEM"
    assert tile_name(-1, -70) == "Copernicus_DSM_COG_10_S01_00_W070_00_DEM"
    assert tile_name(7, 114) == "Copernicus_DSM_COG_10_N07_00_E114_00_DEM"


def test_tile_url_matches_bucket_layout():
    assert tile_url(50, 14) == (
        "https://copernicus-dem-30m.s3.amazonaws.com/"
        "Copernicus_DSM_COG_10_N50_00_E014_00_DEM/"
        "Copernicus_DSM_COG_10_N50_00_E014_00_DEM.tif")
