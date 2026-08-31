"""Pure archive-file helpers and isolated rclone download operations."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath


def archive_remote_path(storage_key: str) -> str:
    raw_key = str(storage_key or '').replace('\\', '/').strip()
    if raw_key.startswith('/'):
        raise ValueError('invalid archive storage key')
    key = raw_key.strip('/')
    path = PurePosixPath(key)
    if not key or path.is_absolute() or '..' in path.parts:
        raise ValueError('invalid archive storage key')
    remote = os.getenv('PDF_ARCHIVE_RCLONE_REMOTE', 'gdrive:archive/pdf').rstrip('/')
    return f'{remote}/{path.as_posix()}'


def download_archive_file(storage_key: str, file_name: str) -> Path:
    rclone_bin = os.getenv('PDF_ARCHIVE_RCLONE_BIN') or shutil.which('rclone')
    if not rclone_bin:
        raise RuntimeError('archive downloader is not configured')
    temp_dir = Path(tempfile.mkdtemp(prefix='ssh-report-archive-'))
    target = temp_dir / (Path(file_name or 'report.pdf').name or 'report.pdf')
    command = [rclone_bin]
    config = os.getenv('PDF_ARCHIVE_RCLONE_CONFIG')
    if config:
        command.extend(['--config', config])
    command.extend(['copyto', archive_remote_path(storage_key), str(target)])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv('PDF_ARCHIVE_DOWNLOAD_TIMEOUT_SECONDS', '45')), check=False)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError('archived PDF is unavailable')
    return target


def remove_download_temp_file(path: Path) -> None:
    shutil.rmtree(path.parent, ignore_errors=True)


def bundle_file_name(file_name: str, report_id: int) -> str:
    name = Path(file_name or f'report-{report_id}.pdf').name
    return name or f'report-{report_id}.pdf'


def remove_bundle_temp_file(path: Path) -> None:
    shutil.rmtree(path.parent, ignore_errors=True)
