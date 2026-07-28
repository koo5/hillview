#!/usr/bin/env python3
"""Bulk-download ČÚZK elevation open data (CC BY 4.0) for the whole Czech
Republic via the INSPIRE ATOM services — the raw input for build_mosaic.py.

Verified service contract (atom.cuzk.gov.cz, 2026-07):
  1. dataset feed   https://atom.cuzk.gov.cz/<DS>/<DS>.xml
     one <entry> per SM5 map sheet: sheet code in
     inspire_dls:spatial_dataset_identifier_code, WGS84 bbox in
     georss:polygon ("lat lon" pairs), rel=alternate link → sheet feed
  2. sheet feed     …/<DS>/datasetFeeds/CZ-00025712-CUZK_<DS>_<SHEET>.xml
     one <entry> per CRS: rel=alternate link → the ZIP on
     https://openzu.cuzk.gov.cz/opendata/<DS>/epsg-<code>/<file>.zip
     with a length attribute; <category term=…EPSG/0/5514> tags the CRS.
     ZIP filenames embed dates and CHANGE — always resolve, never construct.
  (There is also an OpenSearch endpoint atom.cuzk.gov.cz/get.ashx?crs=…&bbox=…
   for ad-hoc area queries; this script sticks to the feeds for bulk work.)

Datasets: dmp1g (surface → DSM rays), dmr5g (bare earth → DTM grounding),
dmr4g (5 m grid, lighter sanity-check option).

Scale warning: whole-CZ DMP 1G + DMR 5G is tens of thousands of sheets and
on the order of hundreds of GB. The script is resumable (skip-if-complete by
size, atomic .part renames, incremental URL cache), polite by default
(4 workers + delay), and filterable (--bbox, --limit) for smoke tests.

Typical whole-country run (from enrich/terrain/):
    python3 download_cuzk.py fetch --dataset dmp1g --out /data/dl/dmp1g --unzip
    python3 download_cuzk.py fetch --dataset dmr5g --out /data/dl/dmr5g --unzip
then rasterize with build_mosaic.py (see README.md).

Stdlib-only on purpose: runs on any box that has python3, nothing else.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

ATOM_BASE = "https://atom.cuzk.gov.cz"
DATASETS = {"dmp1g": "DMP1G-SJTSK", "dmr5g": "DMR5G-SJTSK", "dmr4g": "DMR4G-SJTSK"}
NS = {"a": "http://www.w3.org/2005/Atom",
      "georss": "http://www.georss.org/georss",
      "dls": "http://inspire.ec.europa.eu/schemas/inspire_dls/1.0"}
UA = {"User-Agent": "hillview-terrain/1.0 (github.com/koo5/hillview)"}


@dataclass
class Sheet:
    code: str
    feed_url: str
    bbox: tuple[float, float, float, float]  # lonmin, latmin, lonmax, latmax
    zip_url: str | None = None
    zip_length: int | None = None


# ---------------------------------------------------------------------------
# feed parsing (pure — unit-tested against real service XML in fixtures)
# ---------------------------------------------------------------------------

def polygon_bbox(georss_text: str) -> tuple[float, float, float, float]:
    """georss:polygon is 'lat lon' pairs → (lonmin, latmin, lonmax, latmax)."""
    v = [float(x) for x in georss_text.split()]
    lats, lons = v[0::2], v[1::2]
    return (min(lons), min(lats), max(lons), max(lats))


def bbox_intersects(a: tuple[float, float, float, float],
                    b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def parse_dataset_feed(xml_text: str) -> list[Sheet]:
    root = ET.fromstring(xml_text)
    sheets = []
    for e in root.findall("a:entry", NS):
        ident = e.findtext("dls:spatial_dataset_identifier_code", "", NS)
        poly = e.findtext("georss:polygon", "", NS)
        alt = next((l.get("href") for l in e.findall("a:link", NS)
                    if l.get("rel") == "alternate"), None)
        if not (ident and poly and alt):
            continue
        sheets.append(Sheet(code=ident.rsplit("_", 1)[-1], feed_url=alt,
                            bbox=polygon_bbox(poly)))
    return sheets


def parse_sheet_feed(xml_text: str, epsg: str = "5514") -> tuple[str, int | None]:
    """→ (zip_url, length) of the entry categorised with the wanted EPSG."""
    root = ET.fromstring(xml_text)
    fallback = None
    for e in root.findall("a:entry", NS):
        link = next((l for l in e.findall("a:link", NS)
                     if l.get("rel") == "alternate"), None)
        if link is None:
            continue
        got = (link.get("href"), int(link.get("length")) if link.get("length") else None)
        fallback = fallback or got
        for c in e.findall("a:category", NS):
            if (c.get("term") or "").endswith(f"/EPSG/0/{epsg}"):
                return got
    if fallback is None:
        raise ValueError("sheet feed contains no downloadable entry")
    return fallback


# ---------------------------------------------------------------------------
# network + state
# ---------------------------------------------------------------------------

def http_get(url: str, retries: int = 3, timeout: float = 120.0) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — retry any transient failure
            if attempt == retries - 1:
                raise
            time.sleep(2.0 * (attempt + 1))
            print(f"  retry {url}: {e}", file=sys.stderr)
    raise AssertionError("unreachable")


def load_index(out: Path, dataset: str, refresh: bool) -> list[Sheet]:
    idx = out / "index.json"
    if idx.exists() and not refresh:
        cached = [Sheet(**{**d, "bbox": tuple(d["bbox"])})
                  for d in json.loads(idx.read_text())]
        # an empty cached index is always a poisoned artifact of a past bad
        # fetch, not reality (DMP1G alone has ~16k sheets) — refetch instead
        # of filtering every future bbox to zero forever
        if cached:
            return cached
        print("cached index is EMPTY — refetching the dataset feed")
    ds = DATASETS[dataset]
    print(f"fetching dataset feed {ATOM_BASE}/{ds}/{ds}.xml …")
    sheets = parse_dataset_feed(http_get(f"{ATOM_BASE}/{ds}/{ds}.xml").decode("utf-8"))
    if not sheets:
        raise RuntimeError(f"dataset feed for {ds} parsed to 0 sheets — "
                           "service hiccup or feed format change; not caching")
    out.mkdir(parents=True, exist_ok=True)
    save_index(out, sheets)
    print(f"  {len(sheets)} sheets indexed")
    return sheets


def save_index(out: Path, sheets: list[Sheet]) -> None:
    tmp = out / "index.json.part"
    tmp.write_text(json.dumps([asdict(s) for s in sheets], indent=0))
    tmp.replace(out / "index.json")


def want_download(dest: Path, expected_len: int | None) -> bool:
    """Skip-if-complete: a file of exactly the advertised size is done."""
    if not dest.exists():
        return True
    if expected_len is None:
        return False               # exists and no size to check against: keep
    return dest.stat().st_size != expected_len


def fetch_sheet(sheet: Sheet, out: Path, epsg: str, unzip: bool, sleep: float) -> str:
    if sheet.zip_url is None:
        sheet.zip_url, sheet.zip_length = parse_sheet_feed(
            http_get(sheet.feed_url).decode("utf-8"), epsg)
        time.sleep(sleep)
    dest = out / "zips" / sheet.zip_url.rsplit("/", 1)[-1]
    if want_download(dest, sheet.zip_length):
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = http_get(sheet.zip_url)
        if sheet.zip_length is not None and len(data) != sheet.zip_length:
            raise IOError(f"{sheet.code}: got {len(data)} bytes, "
                          f"feed advertised {sheet.zip_length}")
        part = dest.with_suffix(".part")
        part.write_bytes(data)
        part.replace(dest)          # atomic: a .zip on disk is a complete .zip
        time.sleep(sleep)
        status = f"downloaded {len(data) >> 20} MiB"
    else:
        status = "up to date"
    if unzip:
        laz_dir = out / "laz"
        laz_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest) as z:
            for m in z.namelist():
                if m.lower().endswith((".laz", ".las")) \
                        and not (laz_dir / Path(m).name).exists():
                    z.extract(m, laz_dir)
    return f"{sheet.code}: {status}"


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_index(a: argparse.Namespace) -> None:
    sheets = load_index(a.out, a.dataset, refresh=True)
    resolved = sum(1 for s in sheets if s.zip_url)
    known = sum(s.zip_length or 0 for s in sheets)
    print(f"{len(sheets)} sheets, {resolved} zip URLs resolved, "
          f"{known >> 30} GiB known so far")


def cmd_fetch(a: argparse.Namespace) -> None:
    # keep the FULL index around: the periodic save_index below must persist
    # all sheets, not the bbox-filtered subset — saving the subset amputated
    # the index on every scoped run (Prague seed cut 16301 → 24, the next
    # bbox then intersected against 24 and found nothing). The resolved zip
    # URLs still land in the saved file: fetch_sheet mutates the same Sheet
    # objects the full list holds.
    all_sheets = load_index(a.out, a.dataset, refresh=False)
    sheets = all_sheets
    if a.bbox:
        box = tuple(float(x) for x in a.bbox.split(","))
        sheets = [s for s in sheets if bbox_intersects(s.bbox, box)]
        print(f"bbox filter: {len(sheets)} sheets")
    if a.limit:
        sheets = sheets[: a.limit]
    done = errs = 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(fetch_sheet, s, a.out, a.epsg, a.unzip, a.sleep): s
                   for s in sheets}
        for fut in cf.as_completed(futures):
            s = futures[fut]
            try:
                msg = fut.result()
                done += 1
                if done % 25 == 0 or "downloaded" in msg:
                    print(f"[{done + errs}/{len(sheets)}] {msg}", flush=True)
            except Exception as e:  # noqa: BLE001 — keep the bulk run alive
                errs += 1
                print(f"[{done + errs}/{len(sheets)}] {s.code} FAILED: {e}",
                      file=sys.stderr, flush=True)
            if (done + errs) % 200 == 0:
                save_index(a.out, all_sheets)   # persist resolved zip URLs
    save_index(a.out, all_sheets)
    print(f"done: {done} ok, {errs} failed"
          + (" — rerun to retry failures (resumable)" if errs else ""))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index", help="(re)fetch the dataset feed sheet list")
    pf = sub.add_parser("fetch", help="resolve + download sheets (resumable)")
    for p in (pi, pf):
        p.add_argument("--dataset", choices=sorted(DATASETS), required=True)
        p.add_argument("--out", type=Path, required=True)
    pf.add_argument("--epsg", default="5514", help="CRS variant to download")
    pf.add_argument("--bbox", help="lonmin,latmin,lonmax,latmax filter (WGS84)")
    pf.add_argument("--limit", type=int, help="first N sheets (smoke tests)")
    pf.add_argument("--workers", type=int, default=4, help="polite default: 4")
    pf.add_argument("--sleep", type=float, default=0.1,
                    help="pause per request per worker, seconds")
    pf.add_argument("--unzip", action="store_true",
                    help="extract .laz next to the zips (into <out>/laz)")
    a = ap.parse_args(argv)
    {"index": cmd_index, "fetch": cmd_fetch}[a.cmd](a)


if __name__ == "__main__":
    main()
