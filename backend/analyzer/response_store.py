"""Immutable per-response storage, alongside read-compatible legacy histories."""
import os
from pathlib import Path
from distill import load_sessions, save_sessions, file_lock, lock_path_for


def response_dir(datadir, photo):
    return Path(datadir)/'responses'/photo.file_md5


def has_responses(datadir, photo):
    return (Path(datadir)/f'{photo.file_md5}.json').exists() or response_dir(datadir, photo).is_dir()


def load_photo_sessions(datadir, photo):
    # Caller holds the same photo lock used for the legacy history.
    rows=load_sessions(Path(datadir)/f'{photo.file_md5}.json', lock=False)
    for path in sorted(response_dir(datadir,photo).glob('*.json')):
        session=load_sessions(path,lock=False)
        metadata=session.get('metadata',{})
        if metadata.get('photo_id')==str(photo.id) and metadata.get('file_md5')==photo.file_md5:
            rows.append(session)
    return rows


def immutable_json(path, value):
    path=Path(path)
    with file_lock(lock_path_for(path)):
        if path.exists():
            if load_sessions(path,lock=False)!=value:
                raise ValueError(f'Immutable response differs: {path}')
            return
        save_sessions(path,value,lock=False)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
