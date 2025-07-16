#!/usr/bin/env python3

# sudo apt install jpegoptim imagemagick-6.q16

import os
import shutil
from pathlib import Path
import json
import fire
import exifread
import shlex
import subprocess

from exifread.exif_log import setup_logger

#setup_logger(debug=True, color=False)

from anonymize import anonymize_image

extensions = ['.jpg', '.jpeg', '.tiff', '.png', '.heic', '.heif']


def geo_and_bearing_exif(filepath):
    """
    Check if the image at `filepath` contains both GPS (lat/long)
    and bearing (direction) EXIF data.
    """
    # Possible EXIF keys for bearing info (not all cameras use the same tags):
    # - 'GPS GPSImgDirection'
    # - 'GPS GPSTrack'
    # - 'GPS GPSDestBearing'
    # Some cameras might use different or additional tags,
    # but these are the common ones.

    print()
    print(f"Processing EXIF data from {filepath}")

    # First try exifread
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, details=True, debug=False)

        if len(tags) > 0:
            print("EXIF tags found:", len(tags), "tags")

            bearing = None
            latitude = tags.get('GPS GPSLatitude')
            longitude = tags.get('GPS GPSLongitude')
            
            if latitude and longitude:
                # Check bearing data (any one of the possible keys)
                bearing_keys = ['GPS GPSImgDirection', 'GPS GPSTrack', 'GPS GPSDestBearing']
                for key in bearing_keys:
                    if key in tags:
                        bearing = tags.get(key)
                        break

                if bearing:
                    altitude = tags.get('GPS GPSAltitude')
                    print(f"Found GPS data via exifread")
                    return latitude, longitude, bearing, altitude
    except:
        pass

    # Fallback to exiftool
    try:
        # Use -n flag to get raw numeric values instead of formatted strings
        cmd = ['exiftool', '-json', '-n', '-GPS*', filepath]
        print(f"Trying exiftool fallback: {shlex.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error running exiftool")
            return False
            
        data = json.loads(result.stdout)[0]
        
        # Check for required GPS data
        latitude = data.get('GPSLatitude')
        longitude = data.get('GPSLongitude')
        lat_ref = data.get('GPSLatitudeRef')
        lon_ref = data.get('GPSLongitudeRef')
        
        if latitude is None or longitude is None:
            print(f"No GPS data found.")
            return False
            
        # Convert decimal degrees to [deg, min, sec] format like exifread expects
        def decimal_to_dms(decimal):
            abs_decimal = abs(decimal)
            deg = int(abs_decimal)
            min_decimal = (abs_decimal - deg) * 60
            min_int = int(min_decimal)
            sec_decimal = (min_decimal - min_int) * 60
            # Return as rational - use exifread's Ratio class
            from exifread.classes import Ratio
            sec_rational = Ratio(int(sec_decimal * 1000), 1000)
            return [deg, min_int, sec_rational]
        
        # Apply sign based on reference
        if lat_ref == 'S':
            latitude = -abs(latitude)
        if lon_ref == 'W':
            longitude = -abs(longitude)
            
        lat_dms = decimal_to_dms(latitude)
        lon_dms = decimal_to_dms(longitude)
        
        # Check bearing data
        bearing = data.get('GPSImgDirection') or data.get('GPSTrack') or data.get('GPSDestBearing')
        
        if not bearing:
            print(f"No bearing data found in {filepath}")
            return False
            
        altitude = data.get('GPSAltitude')
        
        # Return in format similar to exifread
        print(f"Found GPS data via exiftool")
        return lat_dms, lon_dms, bearing, altitude
        
    except Exception as e:
        print(f"Error reading EXIF data from {filepath}: {e}")
        return False

def copy_photos_with_bearing_and_gps(source_dir, dest_dir, extensions=None):
    """
    Recursively traverse `source_dir`, detect images with GPS and bearing EXIF data,
    and copy them to `dest_dir`.

    :param source_dir: Source directory to begin recursive search
    :param dest_dir: Destination directory to copy matching images
    :param extensions: List of file extensions to consider as images (e.g. ['.jpg', '.jpeg', '.png'])
                      If None, a default set of image extensions is used.
    """


    # Create destination directory if it doesn't exist
    os.makedirs(dest_dir, exist_ok=True)

    for root, dirs, files in os.walk(source_dir):
        for file in files:

            source_filepath = Path(os.path.join(root, file))
            if source_filepath.is_relative_to(dest_dir):
                continue

            if is_pic(file):

                try:
                    src_size = os.path.getsize(source_filepath)
                except FileNotFoundError:
                    print(f"Skipping unreadable {source_filepath}")
                    continue
                if (src_size < 1000):
                    print(f"Skipping empty {source_filepath}")
                    continue
                if (src_size > 50000000):
                    print(f"Skipping large {source_filepath}")
                    continue

                # Check EXIF for GPS + bearing
                if geo_and_bearing_exif(source_filepath) != False:
                    destination_filepath = os.path.join(dest_dir, file)

                    # if the source file is bigger than the destination file, copy it
                    try:
                        if src_size <= os.path.getsize(destination_filepath):
                            print(f"Skipping smaller {source_filepath}")
                            continue
                    except FileNotFoundError:
                        pass

                    print(f"Copying {source_filepath}")
                    shutil.copy2(source_filepath, destination_filepath)

def is_pic(file):
    """check if the file is a picture"""
    file_lower = file.lower()
    return any(file_lower.endswith(ext) for ext in extensions)


def imgsize(file):
    cmd = ['identify', '-format', '%w %h', file]
    #print('imgsize cmd:', shlex.join(cmd))
    o = subprocess.check_output(cmd).decode('utf-8')
    #print('imgsize o:', o)
    r = [int(x) for x in o.split()]
    print('imgsize r:', r)
    return r


class Geo:
    @staticmethod
    def collect(source_directory = "/d/sync", destination_directory = "/d/sync/jj/geo/pics"):
        """collect all photos with geo and bearing exif data"""

        copy_photos_with_bearing_and_gps(source_directory, destination_directory)
        os.system('fdupes -S -r --delete --noprompt ' + destination_directory)

    @staticmethod
    def process(*source_directories, directory, overwrite=False):
        """Process photos from multiple directories: index and optimize in one pass
        
        Args:
            *source_directories: One or more source directories to process
            directory: Output directory for processed files and JSON index
            overwrite: Whether to reprocess existing files
        """
        
        os.makedirs(directory, exist_ok=True)
        
        # Load existing processed files
        have_files = {}
        try:
            files_path = os.path.join(directory, 'files.json')
            with open(files_path, 'r') as f:
                old = json.load(f)
                for file in old:
                    have_files[file['filepath']] = file
            print(f'Loaded {len(have_files)} existing files from files.json')
        except FileNotFoundError:
            print('No existing files.json found, starting fresh')
            
        database = []
        errors = []
        total_scanned = 0
        total_skipped = 0
        
        for source_directory in source_directories:
            source_directory = os.path.abspath(source_directory)
            if not os.path.exists(source_directory):
                print(f'Warning: Source directory "{source_directory}" does not exist, skipping...')
                continue
                
            print(f'\nProcessing directory: {source_directory}')
            source_name = os.path.basename(source_directory.rstrip('/'))
            
            for root, dirs, files in os.walk(source_directory):
                for filename in sorted(files):
                    if not is_pic(filename):
                        continue
                        
                    filepath = os.path.abspath(os.path.join(root, filename))
                    total_scanned += 1
                    
                    # Skip if already processed
                    if filepath in have_files and not overwrite:
                        database.append(have_files[filepath])
                        total_skipped += 1
                        continue
                    
                    # Check file size
                    try:
                        size = os.path.getsize(filepath)
                        if size < 1000:
                            print(f"Skipping empty {filepath}")
                            continue
                        if size > 50000000:
                            print(f"Skipping large {filepath}")
                            continue
                    except:
                        continue
                    
                    # Check EXIF for GPS + bearing
                    tags = geo_and_bearing_exif(filepath)
                    if not tags:
                        print(f'Skipping non-geo "{filepath}"')
                        continue
                        
                    latitude, longitude, bearing, altitude = tags
                    
                    # Create entry
                    entry = {
                        'filepath': filepath,
                        'file': source_name + '/' + filename,
                        'dir_name': source_name,
                        'latitude': str(latitude),
                        'longitude': str(longitude),
                        'bearing': str(bearing),
                        'sizes': {}
                    }
                    if altitude is not None:
                        entry['altitude'] = str(altitude)
                    
                    # Process image sizes
                    try:
                        print(f'\nProcessing: {filepath}')
                        width, height = imgsize(filepath)
                        
                        # Anonymize
                        input_file_path = filepath
                        anon_dir = '/tmp/geo_anon'
                        anon_file_path = os.path.join(anon_dir, filename)
                        os.makedirs(anon_dir, exist_ok=True)
                        
                        input_dir = os.path.dirname(filepath)
                        if anonymize_image(input_dir, anon_dir, filename):
                            input_file_path = anon_file_path
                            print('anonymized')
                        
                        # Create optimized versions
                        for size in ['full', 50, 320, 640, 1024, 1600, 2048, 2560, 3072]:
                            size_dir = os.path.join('opt', str(size), source_name)
                            size_path = os.path.join(size_dir, filename)
                            output_file_path = os.path.join(directory, size_path)
                            os.makedirs(os.path.join(directory, size_dir), exist_ok=True)
                            
                            if size == 'full':
                                shutil.copy2(input_file_path, output_file_path)
                                entry['sizes'][size] = {
                                    'width': width,
                                    'height': height,
                                    'path': size_path
                                }
                            else:
                                if size > width:
                                    break
                                shutil.copy2(input_file_path, output_file_path)
                                cmd = ['mogrify', '-resize', str(size), output_file_path]
                                subprocess.run(cmd, capture_output=True)
                                w, h = imgsize(output_file_path)
                                entry['sizes'][size] = {
                                    'width': w,
                                    'height': h,
                                    'path': size_path
                                }
                            
                            cmd = ['jpegoptim', '--all-progressive', '--overwrite', output_file_path]
                            subprocess.run(cmd, capture_output=True)
                            
                    except Exception as e:
                        errors.append({
                            'filepath': filepath,
                            'file': filename,
                            'error': str(e)
                        })
                        print(f'Error: {e}')
                        continue
                    
                    database.append(entry)
                    print(f'Processed ({len(database)} total)')
                    
                    # Save progress periodically
                    if len(database) % 10 == 0:
                        sorted_db = sorted(database, key=lambda x: x.get('bearing', ''))
                        with open(os.path.join(directory, 'files_temp.json'), 'w') as f:
                            json.dump(sorted_db, f, indent=4)
        
        # Final save
        database.sort(key=lambda x: x.get('bearing', ''))
        
        files0_path = os.path.join(directory, 'files0.json')
        files_path = os.path.join(directory, 'files.json')
        
        with open(files0_path, 'w') as f:
            json.dump(database, f, indent=4)
        shutil.copy2(files0_path, files_path)
        
        if errors:
            with open(os.path.join(directory, 'errors.json'), 'w') as f:
                json.dump(errors, f, indent=4)
        
        print(f'\nProcessing complete:')
        print(f'- Scanned: {total_scanned} files')
        print(f'- Skipped (already done): {total_skipped} files')
        print(f'- Processed: {len(database) - total_skipped} new files')
        print(f'- Total in database: {len(database)} files')
        print(f'- Errors: {len(errors)}')
    
    @staticmethod
    def index(source_directory, directory):
        """iterate all files and create a json list of files with geo and bearing exif data"""

        os.makedirs(directory, exist_ok=True)

        database = []
        files = sorted([f for f in os.listdir(source_directory) if os.path.isfile(os.path.join(source_directory, f))])
        print(str(len(files)) + ' files indexing...');
        for file in files:
            if is_pic(file):
                filepath = os.path.join(source_directory, file)
                tags = geo_and_bearing_exif(filepath)
                if tags:
                    latitude, longitude, bearing, altitude = tags
                    entry = {
                        'file': file,
                        'latitude': str(latitude),
                        'longitude': str(longitude),
                        'bearing': str(bearing)
                    }
                    # Only add altitude if it exists
                    if altitude is not None:
                        entry['altitude'] = str(altitude)
                    database.append(entry)
                    print(f'Added "{file}" ({len(database)} entries..)')
                else:
                    print(f'Skipping non-geo "{file}"')
            else:
                print(f'Skipping non-pic "{file}"')
        json_file = os.path.join(directory, 'files0.json')
        with open(json_file, 'w') as f:
            json.dump(database, f, indent=4)
        print('indexing done, indexed ' + str(len(database)) + ' files, written to ' + json_file)


    @staticmethod
    def optimize(source_directory, directory, overwrite=False):
        """generate different sizes of the images and optimize them"""

        f = open(directory + '/files0.json')
        files = json.load(f)
        f.close()

        for file in files:
            file['sizes'] = {}

        result = []
        errors = []

        print('optimize ' + str(len(files)) + ' files');


        have_files = {}
        try:
            old_fn = directory + '/files.json'
            print('loading old files from:', old_fn)
            with open(old_fn, 'r') as f:
                old = json.load(f)
                for file in old:
                    have_files[file['file']] = file
        except FileNotFoundError:
            print('no files.json found, creating new one')


        for file in files:
            if file['file'] in have_files:
                file = have_files[file['file']]
                print('file already processed:', file['file'])
                result.append(file)
                continue
            try:
                input_file_path = source_directory + '/' + file['file']

                print()
                print('file:', file['file'])
                width, height = imgsize(input_file_path)
                #print('width:', width, 'height:', height)

                anon_dir = '/tmp/geo_anon';
                anon_file_path = anon_dir + '/' + file['file']
                os.makedirs(anon_dir, exist_ok=True)
                if anonymize_image(source_directory, anon_dir, file['file']):
                    input_file_path = anon_file_path
                    print('anonymized:', input_file_path)

                for size in ['full', 50, 320, 640, 1024, 1600, 2048, 2560, 3072]:

                    size_dir = 'opt/' + str(size)
                    size_path = size_dir + '/' + file['file']# + '.webp'
                    output_file_path = directory + '/' + size_path
                    os.makedirs(directory + '/' + size_dir, exist_ok=True)
                    exists = os.path.exists(output_file_path)

                    if size == 'full':
                        if overwrite or not exists:
                            shutil.copy2(input_file_path, output_file_path)
                        file['sizes'][size] = {'width': width, 'height': height, 'path': size_path}
                    else:
                        if size > width:
                            break
                        else:
                            if overwrite or not exists:
                                shutil.copy2(input_file_path, output_file_path)
                                cmd = ['mogrify', '-resize', str(size), output_file_path]
                                print('cmd:', shlex.join(cmd))
                                subprocess.run(cmd)
                            w,h = imgsize(output_file_path)
                            file['sizes'][size] = {'width': w, 'height': h, 'path': size_path}

                    if overwrite or not exists:
                        cmd = ['jpegoptim', '--all-progressive', '--overwrite', output_file_path]
                        print('cmd:', shlex.join(cmd))
                        subprocess.run(cmd)
                print('db:', file)
            except Exception as e:
                errors.append({
                    'file': file['file'],
                    'error': str(e)
                })
                print('error:', e);

            result.append(file)
            result.sort(key=lambda x: x['bearing'])

            with open(directory + '/files1.json', 'w') as f:
                json.dump(result, f, indent=4)

            with open(directory + '/errors1.json', 'w') as f:
                json.dump(errors, f, indent=4)

        with open(directory + '/files1.json', 'w') as f:
            json.dump(result, f, indent=4)

        with open(directory + '/errors1.json', 'w') as f:
            json.dump(errors, f, indent=4)

        shutil.copy2(directory + '/files1.json', directory + '/files.json')



if __name__ == "__main__":
    fire.Fire(Geo)

