"""download_cuzk.py tests — the XML fixtures are verbatim excerpts of the
live atom.cuzk.gov.cz responses (captured 2026-07), so these pin the parsing
to the real service contract without any network."""
from pathlib import Path

import pytest

from download_cuzk import (Sheet, bbox_intersects, parse_dataset_feed,
                           parse_sheet_feed, polygon_bbox, want_download)

DATASET_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:georss="http://www.georss.org/georss"
      xmlns:inspire_dls="http://inspire.ec.europa.eu/schemas/inspire_dls/1.0"
      xmlns="http://www.w3.org/2005/Atom" xml:lang="cs">
  <id>https://atom.cuzk.cz/DMP1G-SJTSK/DMP1G-SJTSK.xml</id>
  <entry>
    <id>https://atom.cuzk.cz/DMP1G-SJTSK/datasetFeeds/CZ-00025712-CUZK_DMP1G-SJTSK_BENE09.xml</id>
    <title>DMP 1G - S-JTSK - mapovy list: Benesov 0-9</title>
    <link href="https://geoportal.cuzk.cz/SDIProCSW/service.svc/get?Id=X"
          title="metadata datasetu" type="application/xml" rel="describedby" />
    <link href="https://atom.cuzk.cz/DMP1G-SJTSK/datasetFeeds/CZ-00025712-CUZK_DMP1G-SJTSK_BENE09.xml"
          rel="alternate" title="dataset feed" type="application/atom+xml" />
    <category label="S-JTSK" term="http://www.opengis.net/def/crs/EPSG/0/5514" />
    <inspire_dls:spatial_dataset_identifier_code>CZ-00025712-CUZK_DMP1G-SJTSK_BENE09</inspire_dls:spatial_dataset_identifier_code>
    <georss:polygon>49.7764 14.6982 49.7764 14.7363 49.7972 14.7363 49.7972 14.6982 49.7764 14.6982</georss:polygon>
  </entry>
  <entry>
    <id>no-alternate-link-entry-must-be-skipped</id>
  </entry>
</feed>"""

SHEET_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:georss="http://www.georss.org/georss"
      xmlns:inspire_dls="http://inspire.ec.europa.eu/schemas/inspire_dls/1.0" xml:lang="cs">
   <id>https://atom.cuzk.gov.cz/X/datasetFeeds/Y.xml</id>
   <entry>
      <id>https://openzu.cuzk.gov.cz/opendata/X/epsg-3045/X-3045-20260706.zip</id>
      <link href="https://openzu.cuzk.gov.cz/opendata/X/epsg-3045/X-3045-20260706.zip"
            length="6732298971" rel="alternate" type="application/zip" hreflang="cs" />
      <category label="ETRS89/TM33" term="http://www.opengis.net/def/crs/EPSG/0/3045" />
   </entry>
   <entry>
      <id>https://openzu.cuzk.gov.cz/opendata/X/epsg-5514/X-5514-20260706.zip</id>
      <link href="https://openzu.cuzk.gov.cz/opendata/X/epsg-5514/X-5514-20260706.zip"
            length="5795632244" rel="alternate" type="application/zip" hreflang="cs" />
      <category label="S-JTSK" term="http://www.opengis.net/def/crs/EPSG/0/5514" />
   </entry>
</feed>"""


def test_parse_dataset_feed_real_shape():
    sheets = parse_dataset_feed(DATASET_FEED)
    assert len(sheets) == 1                      # malformed entry skipped
    s = sheets[0]
    assert s.code == "BENE09"
    assert s.feed_url.endswith("_BENE09.xml")
    lonmin, latmin, lonmax, latmax = s.bbox
    assert (lonmin, latmax) == (14.6982, 49.7972)
    assert latmin < latmax and lonmin < lonmax


def test_parse_sheet_feed_selects_epsg_5514():
    url, length = parse_sheet_feed(SHEET_FEED, "5514")
    assert "epsg-5514" in url and url.endswith(".zip")
    assert length == 5795632244


def test_parse_sheet_feed_other_crs_and_fallback():
    url, _ = parse_sheet_feed(SHEET_FEED, "3045")
    assert "epsg-3045" in url
    url, _ = parse_sheet_feed(SHEET_FEED, "9999")   # unknown → first entry
    assert "epsg-3045" in url
    with pytest.raises(ValueError):
        parse_sheet_feed("<feed xmlns='http://www.w3.org/2005/Atom'/>")


def test_polygon_bbox_lat_lon_order():
    # georss is "lat lon" pairs — the classic trap; bbox is lon-first
    assert polygon_bbox("50.0 14.0 50.2 14.5") == (14.0, 50.0, 14.5, 50.2)


def test_bbox_intersects():
    cz = (12.0, 48.5, 19.0, 51.1)
    assert bbox_intersects((14.69, 49.77, 14.74, 49.80), cz)
    assert not bbox_intersects((20.0, 49.0, 21.0, 50.0), cz)
    assert bbox_intersects((11.9, 48.4, 12.1, 48.6), cz)     # edge overlap


def test_load_index_refetches_poisoned_empty_cache(tmp_path: Path, monkeypatch):
    """An EMPTY cached index.json (artifact of a past bad fetch) must refetch
    instead of filtering every future bbox to zero forever — the Mělník
    on-demand build found '0 sheets' exactly this way (2026-07-28)."""
    import download_cuzk as dc
    (tmp_path / "index.json").write_text("[]")
    monkeypatch.setattr(dc, "http_get", lambda url: DATASET_FEED.encode())
    sheets = dc.load_index(tmp_path, "dmp1g", refresh=False)
    assert [s.code for s in sheets] == ["BENE09"]
    # and the refreshed (non-empty) index landed on disk
    assert "BENE09" in (tmp_path / "index.json").read_text()


def test_load_index_never_caches_an_empty_parse(tmp_path: Path, monkeypatch):
    import download_cuzk as dc
    empty = DATASET_FEED.split("<entry>")[0] + "</feed>"
    monkeypatch.setattr(dc, "http_get", lambda url: empty.encode())
    with pytest.raises(RuntimeError, match="0 sheets"):
        dc.load_index(tmp_path, "dmp1g", refresh=False)
    assert not (tmp_path / "index.json").exists()


def test_fetch_bbox_run_keeps_the_full_index(tmp_path: Path, monkeypatch):
    """A bbox-scoped fetch must not amputate index.json to its own subset —
    the Prague seed build did exactly that (16301 → 24 → 0 for the next
    bbox), which is how on-demand Mělník found '0 sheets'."""
    import argparse

    import download_cuzk as dc
    monkeypatch.setattr(dc, "http_get", lambda url: DATASET_FEED.encode())
    a = argparse.Namespace(out=tmp_path, dataset="dmp1g",
                           bbox="10.0,40.0,10.5,40.5",   # misses BENE09
                           limit=None, workers=1, epsg="5514",
                           unzip=False, sleep=0.0)
    dc.cmd_fetch(a)
    assert "BENE09" in (tmp_path / "index.json").read_text()


def test_want_download_skip_if_complete(tmp_path: Path):
    f = tmp_path / "a.zip"
    assert want_download(f, 100)                 # missing → download
    f.write_bytes(b"x" * 100)
    assert not want_download(f, 100)             # exact size → skip
    assert want_download(f, 200)                 # size mismatch → redo
    assert not want_download(f, None)            # exists, size unknown → keep
