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
        "bbox": ",".join(map(str, [top_left_lon, top_left_lat, bottom_right_lon, bottom_right_lat])),
        "fields": "id,geometry,compass_angle,thumb_1024_url",
        "access_token": TOKEN,
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    if 'data' in data:
        sorted_data = sorted(data['data'], key=lambda x: x['compass_angle'])
        log.info(f"Found {len(sorted_data)} images")
        return sorted_data
