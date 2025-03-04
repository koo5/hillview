from fastapi import FastAPI, Query
from typing import List
import os
import json
import requests
import logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

TOKEN = open(os.path.expanduser(os.environ['MAPILLARY_CLIENT_TOKEN_FILE'])).read().strip()
url = "https://graph.mapillary.com/images"

app = FastAPI()

@app.get("/api/mapillary")
def get_images(top_left_lat: float = Query(..., description="Top left latitude"),
               top_left_lon: float = Query(..., description="Top left longitude"),
               bottom_right_lat: float = Query(..., description="Bottom right latitude"),
               bottom_right_lon: float = Query(..., description="Bottom right longitude")):
    params = {
        "limit": 200,
        "bbox": ",".join(map(str, [round(top_left_lon, 7), round(bottom_right_lat,7), round(bottom_right_lon,7), round(top_left_lat,7)])),
        "fields": "id,geometry,compass_angle,thumb_1024_url",
        "access_token": TOKEN,
    }
    resp = requests.get(url, params=params)
    rr = resp.json()
    log.debug(json.dumps(rr, indent=2))
    if 'data' in rr:
        sorted_data = sorted(rr['data'], key=lambda x: x['compass_angle'])
        log.info(f"Found {len(sorted_data)} images")
        #log.info(f"paging: {rr.get('paging')}")
        return sorted_data
    else:
        log.error(f"Error: {rr}")
        return []
