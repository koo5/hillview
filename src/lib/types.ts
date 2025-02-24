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
    loaded?: boolean;
}

export interface MapState {
    center: Coordinate;
    zoom: number;
    bearing: number;
    range: number;
}
