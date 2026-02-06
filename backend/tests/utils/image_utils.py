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


SOLAR_SYSTEM_FACTS = [
    "The Sun contains 99.86% of\nthe mass in our solar system.",
    "Jupiter's Great Red Spot is\na storm larger than Earth.",
    "Saturn's rings are made of\nice and rock particles.",
    "A day on Venus is longer\nthan its year.",
    "Mars has the tallest volcano:\nOlympus Mons at 21.9 km.",
    "Neptune's winds reach\n2,100 km/h.",
    "Mercury's temperature swings\nfrom -180°C to 430°C.",
    "Uranus rotates on its side\nat a 98° tilt.",
    "Earth is the only planet\nnot named after a god.",
    "The Moon is slowly drifting\naway from Earth.",
]

UNIT_CONVERSION_FACTS = [
    "1 mile = 1.609 kilometers\n1 km = 0.621 miles",
    "1 inch = 2.54 centimeters\n1 cm = 0.394 inches",
    "1 pound = 0.454 kilograms\n1 kg = 2.205 pounds",
    "1 gallon = 3.785 liters\n1 liter = 0.264 gallons",
    "1 foot = 30.48 centimeters\n1 meter = 3.281 feet",
    "1 ounce = 28.35 grams\n1 gram = 0.035 ounces",
    "32°F = 0°C, 212°F = 100°C\n°C = (°F - 32) × 5/9",
    "1 yard = 0.914 meters\n1 meter = 1.094 yards",
    "1 fluid oz = 29.57 mL\n1 mL = 0.034 fluid oz",
    "1 acre = 0.405 hectares\n1 hectare = 2.471 acres",
]


def _draw_info_sign(draw: ImageDraw.Draw, width: int, height: int, facts: list) -> None:
    """Draw an information board with a random fact from the given list."""
    # Sign dimensions and position (foreground, bottom area)
    sign_width = min(width // 2, 300)
    sign_height = min(height // 3, 150)
    sign_x = random.randint(width // 6, width - sign_width - width // 6)
    sign_y = height - sign_height - random.randint(10, height // 6)

    # Post
    post_width = max(8, sign_width // 15)
    post_x = sign_x + sign_width // 2 - post_width // 2
    draw.rectangle([post_x, sign_y + sign_height, post_x + post_width, height],
                   fill=(80, 60, 40))

    # Sign board
    board_color = (60, 40, 20)
    draw.rectangle([sign_x, sign_y, sign_x + sign_width, sign_y + sign_height],
                   fill=board_color, outline=(40, 25, 10), width=3)

    # Inner frame
    margin = max(5, sign_width // 20)
    inner_color = (245, 235, 200)
    draw.rectangle([sign_x + margin, sign_y + margin,
                    sign_x + sign_width - margin, sign_y + sign_height - margin],
                   fill=inner_color)

    # Title bar
    title_height = max(15, sign_height // 6)
    draw.rectangle([sign_x + margin, sign_y + margin,
                    sign_x + sign_width - margin, sign_y + margin + title_height],
                   fill=(0, 80, 150))

    # Text (simple representation - PIL default font is tiny)
    fact = random.choice(facts)
    text_x = sign_x + margin + 5
    text_y = sign_y + margin + title_height + 5
    # Draw text line by line
    for i, line in enumerate(fact.split('\n')):
        draw.text((text_x, text_y + i * 12), line, fill=(30, 30, 30))


def _draw_cloud(draw: ImageDraw.Draw, x: int, y: int, size: int) -> None:
    """Draw a fluffy cloud made of overlapping ellipses."""
    cloud_color = (random.randint(230, 255), random.randint(230, 255), random.randint(240, 255))
    num_puffs = random.randint(3, 6)
    for _ in range(num_puffs):
        puff_x = x + random.randint(-size, size)
        puff_y = y + random.randint(-size // 3, size // 3)
        puff_w = random.randint(size // 2, size)
        puff_h = random.randint(size // 3, size // 2)
        draw.ellipse([puff_x - puff_w, puff_y - puff_h, puff_x + puff_w, puff_y + puff_h], fill=cloud_color)


def _draw_mountain(draw: ImageDraw.Draw, x: int, base_y: int, peak_height: int, mtn_width: int) -> None:
    """Draw a triangular mountain with optional snow cap."""
    mountain_colors = [
        (random.randint(60, 100), random.randint(80, 120), random.randint(60, 90)),
        (random.randint(100, 140), random.randint(80, 110), random.randint(60, 80)),
        (random.randint(80, 120), random.randint(80, 120), random.randint(90, 130)),
    ]
    mountain_color = random.choice(mountain_colors)

    peak_x = x + mtn_width // 2
    peak_y = base_y - peak_height
    draw.polygon([(x, base_y), (peak_x, peak_y), (x + mtn_width, base_y)], fill=mountain_color)

    # Snow cap for tall mountains
    if peak_height > 100 and random.random() > 0.5:
        snow_h = peak_height // 4
        snow_w = mtn_width // 4
        draw.polygon([
            (peak_x - snow_w, peak_y + snow_h),
            (peak_x, peak_y),
            (peak_x + snow_w, peak_y + snow_h)
        ], fill=(255, 255, 255))


def _draw_hill(draw: ImageDraw.Draw, x: int, base_y: int, peak_height: int, hill_width: int) -> None:
    """Draw a rounded hill."""
    hill_color = (random.randint(50, 100), random.randint(120, 180), random.randint(50, 100))
    draw.ellipse([x, base_y - peak_height, x + hill_width, base_y + peak_height], fill=hill_color)


def _draw_house(draw: ImageDraw.Draw, x: int, base_y: int, house_width: int, house_height: int) -> None:
    """Draw a simple house with roof, door, and windows."""
    wall_colors = [
        (random.randint(180, 220), random.randint(160, 200), random.randint(140, 180)),
        (random.randint(200, 240), random.randint(200, 240), random.randint(200, 240)),
        (random.randint(180, 220), random.randint(100, 140), random.randint(80, 120)),
    ]
    roof_colors = [
        (random.randint(120, 160), random.randint(60, 100), random.randint(60, 80)),
        (random.randint(60, 100), random.randint(60, 100), random.randint(80, 120)),
    ]

    # House body
    draw.rectangle([x, base_y - house_height, x + house_width, base_y], fill=random.choice(wall_colors))

    # Roof
    roof_height = house_height // 2
    draw.polygon([
        (x - house_width // 8, base_y - house_height),
        (x + house_width // 2, base_y - house_height - roof_height),
        (x + house_width + house_width // 8, base_y - house_height)
    ], fill=random.choice(roof_colors))

    # Door
    door_w = house_width // 4
    door_h = house_height // 2
    door_x = x + (house_width - door_w) // 2
    draw.rectangle([door_x, base_y - door_h, door_x + door_w, base_y],
                   fill=(random.randint(80, 120), random.randint(50, 80), random.randint(30, 60)))

    # Windows
    if house_width > 40:
        win_size = house_width // 6
        win_color = (random.randint(150, 200), random.randint(200, 240), random.randint(230, 255))
        win_y = base_y - house_height + house_height // 4
        draw.rectangle([x + house_width // 6, win_y, x + house_width // 6 + win_size, win_y + win_size],
                       fill=win_color, outline=(50, 50, 50))
        draw.rectangle([x + house_width - house_width // 6 - win_size, win_y,
                        x + house_width - house_width // 6, win_y + win_size],
                       fill=win_color, outline=(50, 50, 50))


def _draw_landscape(draw: ImageDraw.Draw, width: int, height: int) -> None:
    """Draw a naive landscape with sky, mountains/hills, clouds, and houses."""
    horizon_y = int(height * 0.6)

    # Sky
    sky_color = (random.randint(120, 180), random.randint(180, 220), random.randint(230, 255))
    draw.rectangle([0, 0, width, horizon_y], fill=sky_color)

    # Ground
    ground_color = (random.randint(80, 130), random.randint(140, 190), random.randint(80, 120))
    draw.rectangle([0, horizon_y, width, height], fill=ground_color)

    # Mountains or hills in background
    for _ in range(random.randint(2, 5)):
        mtn_x = random.randint(-width // 4, width)
        mtn_width = random.randint(width // 4, width // 2)
        mtn_height = random.randint(height // 6, height // 3)
        if random.random() > 0.5:
            _draw_mountain(draw, mtn_x, horizon_y, mtn_height, mtn_width)
        else:
            _draw_hill(draw, mtn_x, horizon_y, mtn_height, mtn_width)

    # Clouds
    for _ in range(random.randint(2, 6)):
        _draw_cloud(draw, random.randint(0, width), random.randint(height // 10, horizon_y // 2),
                    random.randint(width // 20, width // 8))

    # Small distant houses on horizon
    for _ in range(random.randint(2, 5)):
        _draw_house(draw, random.randint(0, width - 30), horizon_y + 5,
                    random.randint(15, 35), random.randint(10, 25))

    # Medium houses in middle ground
    middle_y = horizon_y + (height - horizon_y) // 3
    for _ in range(random.randint(2, 4)):
        _draw_house(draw, random.randint(0, width - 60), middle_y,
                    random.randint(35, 70), random.randint(25, 50))

    # Large houses in foreground
    front_y = horizon_y + 2 * (height - horizon_y) // 3
    for _ in range(random.randint(1, 3)):
        _draw_house(draw, random.randint(0, width - 120), front_y,
                    random.randint(80, 150), random.randint(60, 100))


def _draw_abstract_shapes(draw: ImageDraw.Draw, width: int, height: int) -> None:
    """Draw random abstract shapes (rectangles, circles, lines)."""
    # Draw random rectangles
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

    # Draw random circles
    max_radius = min(150, min(width, height) // 4)
    margin = max(10, max_radius)

    if width > 2 * margin and height > 2 * margin:
        for _ in range(random.randint(15, 30)):
            x = random.randint(margin, width - margin)
            y = random.randint(margin, height - margin)
            radius = random.randint(5, max_radius)
            circle_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=circle_color)

    # Draw random lines
    for _ in range(random.randint(25, 50)):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        line_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        line_width = random.randint(1, 10)
        draw.line([x1, y1, x2, y2], fill=line_color, width=line_width)


def create_test_image_full_gps(width: int = 2048, height: int = 1536, color: tuple = (255, 255, 0),
                               lat: float = 50.0755, lon: float = 14.4378, bearing: float = 90.0) -> bytes:
    """Create a JPEG image with both GPS coordinates and bearing data."""
    # Validate bearing range
    if bearing < 0 or bearing > 360:
        raise ValueError(f"Invalid bearing value: {bearing}. Must be between 0 and 360 degrees.")

    # Create larger image with more complex content
    img = Image.new('RGB', (width, height), color)
    draw = ImageDraw.Draw(img)

    # Save global random state, seed for deterministic image content, then restore
    saved_state = random.getstate()
    random.seed(int(lat * 1000 + lon * 1000 + bearing))

    # Flip a coin: abstract shapes or landscape
    if random.random() > 0.5:
        _draw_landscape(draw, width, height)
    else:
        _draw_abstract_shapes(draw, width, height)

    # Randomly add info sign (1 or 2 in 100 chance)
    sign_roll = random.randint(1, 100)
    if sign_roll == 1:
        _draw_info_sign(draw, width, height, SOLAR_SYSTEM_FACTS)
    elif sign_roll == 2:
        _draw_info_sign(draw, width, height, UNIT_CONVERSION_FACTS)

    # Restore global random state
    random.setstate(saved_state)

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