#!/usr/bin/env python3
"""
Image generation utilities for photo processing tests.
"""

from PIL import Image, ImageDraw
import piexif
import io
import random


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


def create_test_image_full_gps(width: int = 2048, height: int = 1536, color: tuple = (255, 255, 0),
                               lat: float = 50.0755, lon: float = 14.4378, bearing: float = 90.0) -> bytes:
    """Create a JPEG image with both GPS coordinates and bearing data."""
    # Validate bearing range
    if bearing < 0 or bearing > 360:
        raise ValueError(f"Invalid bearing value: {bearing}. Must be between 0 and 360 degrees.")

    # Create larger image with more complex content
    img = Image.new('RGB', (width, height), color)
    draw = ImageDraw.Draw(img)

    # Add random shapes to make the image more complex and realistic
    random.seed(int(lat * 1000 + lon * 1000 + bearing))  # Deterministic randomness based on GPS data

    # Draw random rectangles - more for larger image
    # Ensure we don't exceed image boundaries
    max_rect_width = min(300, width - 10)
    max_rect_height = min(300, height - 10)
    min_start_x = max(0, width - max_rect_width)
    min_start_y = max(0, height - max_rect_height)

    for _ in range(random.randint(20, 50)):
        x1 = random.randint(0, min_start_x) if min_start_x > 0 else 0
        y1 = random.randint(0, min_start_y) if min_start_y > 0 else 0
        x2 = x1 + random.randint(10, min(max_rect_width, width - x1 - 1))
        y2 = y1 + random.randint(10, min(max_rect_height, height - y1 - 1))
        rect_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.rectangle([x1, y1, x2, y2], fill=rect_color)

    # Draw random circles - more and larger for bigger image
    # Ensure circles fit within image boundaries
    max_radius = min(150, min(width, height) // 4)
    margin = max(10, max_radius)

    if width > 2 * margin and height > 2 * margin:
        for _ in range(random.randint(15, 30)):
            x = random.randint(margin, width - margin)
            y = random.randint(margin, height - margin)
            radius = random.randint(5, max_radius)
            circle_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=circle_color)

    # Draw random lines - more for complexity
    for _ in range(random.randint(25, 50)):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        line_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        line_width = random.randint(1, 10)
        draw.line([x1, y1, x2, y2], fill=line_color, width=line_width)
    
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