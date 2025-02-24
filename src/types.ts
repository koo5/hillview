export interface PhotoData {
  id: string;
  file: string;
  thumbnail: string;
  latitude: number;
  longitude: number;
  direction: number;
  distance?: number;
  altitude?: number;
  loaded?: boolean;
  relativeBearing?: number;
  directionDiff?: number;
}

export interface MapState {
  center: [number, number];
  zoom: number;
  bearing: number;
  maxDistance: number;
}

export interface APIPhotoData {
  file: string;
  latitude: string;
  longitude: string;
  bearing: string;
  altitude: string;
}