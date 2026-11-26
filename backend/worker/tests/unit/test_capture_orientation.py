"""Browser orientation flags must rotate real pixels without rewriting uploads."""
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from blur import read_image
from pyramid_source import RasterSource


class CaptureOrientationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='capture-orientation-')
        self.addCleanup(directory.cleanup)
        self.capture = Path(directory.name) / 'capture.jpg'
        pixels = np.zeros((32, 48, 3), dtype=np.uint8)
        pixels[:16, :24] = (255, 0, 0)
        pixels[:16, 24:] = (0, 255, 0)
        pixels[16:, :24] = (0, 0, 255)
        pixels[16:, 24:] = (255, 255, 0)
        Image.fromarray(pixels).save(self.capture, quality=100, subsampling=0)

    def test_metadata_rotates_pixels_and_the_llm_reread_once(self):
        digest = hashlib.sha256(self.capture.read_bytes()).digest()
        original = read_image(str(self.capture))
        for orientation, turns in ((1, 0), (3, 2), (6, -1), (8, 1)):
            with self.subTest(orientation=orientation):
                expected = np.rot90(original, turns)
                actual = read_image(str(self.capture), orientation_override=orientation)
                np.testing.assert_array_equal(actual, expected)
                source = RasterSource(actual, str(self.capture), None, orientation_override=orientation)
                np.testing.assert_array_equal(source.fresh_for_width(640), expected)
                # The override changes neither upload bytes nor the loader's
                # cached orientation for a later decode without this option.
                self.assertEqual(hashlib.sha256(self.capture.read_bytes()).digest(), digest)
                np.testing.assert_array_equal(read_image(str(self.capture)), original)

    def test_embedded_exif_rotates_once_without_an_override(self):
        original = read_image(str(self.capture))
        with Image.open(self.capture) as image:
            pixels = image.copy()
        exif = Image.Exif()
        exif[274] = 6
        pixels.save(self.capture, quality=100, subsampling=0, exif=exif)
        actual = read_image(str(self.capture))
        self.assertEqual(actual.shape, (48, 32, 3))
        np.testing.assert_allclose(actual, np.rot90(original, -1), atol=3)

    def test_invalid_capture_orientation_is_rejected(self):
        for orientation in (0, 2, 5, 7, 9):
            with self.subTest(orientation=orientation), self.assertRaisesRegex(ValueError, 'Unsupported capture orientation'):
                read_image(str(self.capture), orientation_override=orientation)


if __name__ == '__main__':
    unittest.main()
