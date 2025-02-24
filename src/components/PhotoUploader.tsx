import React, { useCallback } from 'react';
import { Upload } from 'lucide-react';
import ExifReader from 'exifreader';
import { PhotoData } from '../types';

interface Props {
  onPhotosLoaded: (photos: PhotoData[]) => void;
}

function convertDMSToDD(degrees: number, minutes: number, seconds: number, direction: string): number {
  let dd = degrees + minutes / 60 + seconds / 3600;
  if (direction === 'S' || direction === 'W') {
    dd = dd * -1;
  }
  return dd;
}

function parseGPSDirection(direction: any): number {
  if (!direction) return 0;

  // Handle fraction format (e.g., "163/1")
  if (typeof direction.description === 'string' && direction.description.includes('/')) {
    const [numerator, denominator] = direction.description.split('/').map(Number);
    return numerator / denominator;
  }

  // Handle direct number format
  if (typeof direction.description === 'number') {
    return direction.description;
  }

  // Handle array format
  if (Array.isArray(direction.description)) {
    const [degrees, minutes = 0, seconds = 0] = direction.description;
    return degrees + minutes / 60 + seconds / 3600;
  }

  // Try parsing as a simple number
  const value = parseFloat(direction.description);
  return isNaN(value) ? 0 : value;
}

export function PhotoUploader({ onPhotosLoaded }: Props) {
  const processFiles = useCallback(async (files: FileList) => {
    const photos: PhotoData[] = [];

    for (const file of Array.from(files)) {
      if (!file.type.startsWith('image/jpeg')) {
        console.log('Skipping non-JPEG file:', file.name);
        continue;
      }

      try {
        const arrayBuffer = await file.arrayBuffer();
        const tags = await ExifReader.load(arrayBuffer);

        if (!tags.GPSLatitude || !tags.GPSLongitude) {
          console.log('No GPS data found in:', file.name);
          continue;
        }

        // Get GPS references
        const latRef = tags.GPSLatitudeRef?.description || 'N';
        const longRef = tags.GPSLongitudeRef?.description || 'E';

        // Extract GPS coordinates
        const latitude = convertDMSToDD(
          tags.GPSLatitude.description[0],
          tags.GPSLatitude.description[1],
          tags.GPSLatitude.description[2],
          latRef
        );

        const longitude = convertDMSToDD(
          tags.GPSLongitude.description[0],
          tags.GPSLongitude.description[1],
          tags.GPSLongitude.description[2],
          longRef
        );

        // Validate coordinates
        if (isNaN(latitude) || isNaN(longitude) || 
            latitude < -90 || latitude > 90 || 
            longitude < -180 || longitude > 180) {
          console.log('Invalid coordinates found:', { latitude, longitude });
          continue;
        }

        // Get image direction (if available)
        let direction = 0;
        if (tags.GPSImgDirection) {
          direction = parseGPSDirection(tags.GPSImgDirection);
          console.log('Parsed direction:', {
            raw: tags.GPSImgDirection.description,
            parsed: direction
          });
        }

        const thumbnail = URL.createObjectURL(file);

        console.log('Valid coordinates found:', { latitude, longitude, direction });

        photos.push({
          id: Math.random().toString(36).substring(7),
          file,
          thumbnail,
          latitude,
          longitude,
          direction,
        });
      } catch (error) {
        console.error('Error processing file:', file.name, error);
      }
    }

    if (photos.length === 0) {
      console.log('No valid photos with GPS data were found');
    } else {
      console.log('Successfully processed photos:', photos);
      onPhotosLoaded(photos);
    }
  }, [onPhotosLoaded]);

  return (
    <div className="p-4 border-2 border-dashed border-gray-300 rounded-lg text-center">
      <label className="cursor-pointer block">
        <input
          type="file"
          multiple
          accept="image/jpeg"
          className="hidden"
          onChange={(e) => e.target.files && processFiles(e.target.files)}
        />
        <Upload className="mx-auto mb-2" />
        <p>Drop photos or click to upload</p>
        <p className="text-sm text-gray-500">Only JPEG files with GPS data</p>
      </label>
    </div>
  );
}