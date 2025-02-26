import {Coordinate} from "tsgeo/Coordinate";

export interface APIPhotoData {
    file: string;
    latitude: string;
    longitude: string;
    bearing: string;
    altitude: string;
}

export interface Photo {
    id: string;
    file: string;
    url: string;
    coord: Coordinate;
    direction: number;
    altitude?: number;
    abs_bearing_diff: number;
    areas: object[];
}
