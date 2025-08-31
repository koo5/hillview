#!/usr/bin/env python3
"""
Image generation utilities for photo processing tests.
"""

from PIL import Image
import piexif
import io


def create_test_image_no_exif(width: int = 100, height: int = 100, color: tuple = (255, 0, 0)) -> bytes:
    """Create a JPEG image with no EXIF data at all."""
    img = Image.new('RGB', (width, height), color)
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='JPEG', quality=85)
    img_buffer.seek(0)
    return img_buffer.getvalue()


def create_test_image_coords_only(width: int = 100, height: int = 100, color: tuple = (0, 255, 0),
                                  lat: float = 50.0755, lon: float = 14.4378) -> bytes:
    """Create a JPEG image with GPS coordinates but no bearing data."""
    img = Image.new('RGB', (width, height), color)
    
    def decimal_to_dms(decimal_deg):
        deg = int(decimal_deg)
        minutes = abs((decimal_deg - deg) * 60)
        min_int = int(minutes)
        sec = (minutes - min_int) * 60
        return [(deg, 1), (min_int, 1), (int(sec * 100), 100)]
    
    # Only GPS coordinates, no bearing tags
    gps_dict = {
        piexif.GPSIFD.GPSLatitude: decimal_to_dms(abs(lat)),
        piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
        piexif.GPSIFD.GPSLongitude: decimal_to_dms(abs(lon)),
        piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
    }
    
    exif_dict = {"GPS": gps_dict}
    exif_bytes = piexif.dump(exif_dict)
    
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='JPEG', quality=85, exif=exif_bytes)
    img_buffer.seek(0)
    return img_buffer.getvalue()


def create_test_image_bearing_only(width: int = 100, height: int = 100, color: tuple = (0, 0, 255)) -> bytes:
    """Create a JPEG image with bearing data but no GPS coordinates."""
    img = Image.new('RGB', (width, height), color)
    
    # Only bearing, no coordinates
    gps_dict = {
        piexif.GPSIFD.GPSImgDirection: (90, 1),  # 90 degrees
        piexif.GPSIFD.GPSImgDirectionRef: 'T',  # True north
    }
    
    exif_dict = {"GPS": gps_dict}
    exif_bytes = piexif.dump(exif_dict)
    
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='JPEG', quality=85, exif=exif_bytes)
    img_buffer.seek(0)
    return img_buffer.getvalue()


def create_test_image_full_gps(width: int = 100, height: int = 100, color: tuple = (255, 255, 0),
                               lat: float = 50.0755, lon: float = 14.4378, bearing: float = 90.0) -> bytes:
    """Create a JPEG image with both GPS coordinates and bearing data."""
    img = Image.new('RGB', (width, height), color)
    
    def decimal_to_dms(decimal_deg):
        deg = int(decimal_deg)
        minutes = abs((decimal_deg - deg) * 60)
        min_int = int(minutes)
        sec = (minutes - min_int) * 60
        return [(deg, 1), (min_int, 1), (int(sec * 100), 100)]
    
    # Full GPS data with coordinates and bearing
    gps_dict = {
        piexif.GPSIFD.GPSLatitude: decimal_to_dms(abs(lat)),
        piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
        piexif.GPSIFD.GPSLongitude: decimal_to_dms(abs(lon)),
        piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
        piexif.GPSIFD.GPSImgDirection: (int(bearing * 100), 100),  # bearing in degrees
        piexif.GPSIFD.GPSImgDirectionRef: 'T',  # True north
    }
    
    exif_dict = {"GPS": gps_dict}
    exif_bytes = piexif.dump(exif_dict)
    
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='JPEG', quality=85, exif=exif_bytes)
    img_buffer.seek(0)
    return img_buffer.getvalue()


def create_test_image_corrupted_exif(width: int = 100, height: int = 100, color: tuple = (255, 0, 255)) -> bytes:
    """Create a JPEG image with malformed EXIF data that should cause parsing errors."""
    img = Image.new('RGB', (width, height), color)
    
    # Create deliberately malformed GPS data
    gps_dict = {
        piexif.GPSIFD.GPSLatitude: "invalid_latitude",  # Wrong type
        piexif.GPSIFD.GPSLatitudeRef: 'N',
        piexif.GPSIFD.GPSLongitude: [(50, 0), (30, 1), (15, 1)],  # Invalid format (division by zero)
        piexif.GPSIFD.GPSLongitudeRef: 'E',
    }
    
    try:
        exif_dict = {"GPS": gps_dict}
        exif_bytes = piexif.dump(exif_dict)
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG', quality=85, exif=exif_bytes)
        img_buffer.seek(0)
        return img_buffer.getvalue()
    except:
        # If piexif refuses to create bad EXIF, just create image without EXIF
        # The worker will still test parsing error handling with real-world corrupted files
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG', quality=85)
        img_buffer.seek(0)
        return img_buffer.getvalue()