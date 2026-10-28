"""Real decoder regressions for source paths reused by persistent workers.

Each case runs with a fresh worker policy and an enabled libvips operation cache.
No database, uploads or detector models are used. Run with pytest or unittest.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest

WORKER = Path(__file__).resolve().parents[2]


def probe(image_format, replacement):
    import tempfile

    import numpy as np
    from PIL import Image
    import pyvips

    from blur import read_image

    def write(path, size, rgb):
        if image_format == 'exr':
            import OpenEXR

            pixels = np.empty((size[1], size[0], 3), dtype=np.float32)
            pixels[:] = rgb
            with OpenEXR.File({}, {'RGB': pixels}) as output:
                output.write(str(path))
        else:
            Image.new('RGB', size, tuple(c * 255 for c in rgb)).save(
                path, format='JPEG', quality=100, subsampling=0)

    def read(path):
        return read_image(str(path), encoding='srgb' if image_format == 'exr' else None)

    cache_limit = pyvips.cache_get_max()
    assert cache_limit > 0, 'regression requires the normal enabled operation cache'
    with tempfile.TemporaryDirectory(prefix='image-cache-test-') as directory:
        directory = Path(directory)
        old = directory / ('old.' + image_format)
        write(old, (17, 9), (1, 0, 0))
        path = directory / ('input.' + image_format)
        if replacement == 'symlink':
            path.symlink_to(old.name)
        else:
            os.replace(old, path)
        original_stat = path.stat()
        first = read(path)
        assert first.shape == (9, 17, 3)
        np.testing.assert_allclose(first.mean(axis=(0, 1)), [0, 0, 255], atol=2)
        assert pyvips.cache_get_size() > 0, 'first decode did not populate the cache'

        size = (13, 7) if replacement in ('dimensions', 'symlink') else (17, 9)
        new = directory / ('new.' + image_format)
        write(new, size, (0, 1, 0))
        if replacement == 'dimensions':
            os.utime(new, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 120_000_000_000))
        else:
            # Same-size rerenders can preserve timestamps; freshness cannot depend on stat.
            os.utime(new, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        if replacement == 'symlink':
            link = directory / 'replacement-link'
            link.symlink_to(new.name)
            os.replace(link, path)
        else:
            os.replace(new, path)

        current = read(path)
        assert current.shape == (size[1], size[0], 3), (current.shape, size)
        np.testing.assert_allclose(current.mean(axis=(0, 1)), [0, 255, 0], atol=2)
        # The returned first raster remains valid, and global cache policy stays untouched.
        np.testing.assert_allclose(first.mean(axis=(0, 1)), [0, 0, 255], atol=2)
        assert pyvips.cache_get_max() == cache_limit


class ImageLoadCacheTests(unittest.TestCase):
    def check_replacement(self, image_format, replacement, auxiliary):
        env = {**os.environ, 'PYTHONPATH': f'{WORKER}:{WORKER.parent}:{WORKER.parent}/common',
               'HILLVIEW_AUX': str(int(auxiliary))}
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--probe', image_format, replacement],
                                env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-6000:])

    def test_exr_replaced_with_different_dimensions(self):
        self.check_replacement('exr', 'dimensions', True)

    def test_exr_replaced_with_same_dimensions_and_mtime(self):
        self.check_replacement('exr', 'pixels', True)

    def test_exr_symlink_retargeted(self):
        self.check_replacement('exr', 'symlink', True)

    def test_public_jpeg_replaced_with_same_dimensions_and_mtime(self):
        self.check_replacement('jpg', 'pixels', False)

    def test_auxiliary_jpeg_replaced_with_same_dimensions_and_mtime(self):
        self.check_replacement('jpg', 'pixels', True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--probe':
        probe(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
