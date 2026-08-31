from pathlib import Path
from ..exceptions import PermissionDeniedException


def resolve_log_path(sub_path: str | None, log_dir: Path) -> Path:
    if not sub_path:
        return log_dir
    candidate = (log_dir / (sub_path or '')).resolve()
    if candidate != log_dir.resolve() and log_dir.resolve() not in candidate.parents:
        raise PermissionDeniedException('Access denied: path traversal detected')
    return candidate


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.1f} {unit}' if unit != 'B' else f'{int(size)} B'
        size /= 1024
    return f'{size:.1f} GB'


def format_mtime(mtime: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')


def get_description(name: str) -> str | None:
    descriptions = {
        'fix_ls_db': 'LS DB Fix 로그', 'fix_dbfi_urls': 'DB Fi URL Fix 로그',
        'scheduler': '스케줄러 실행 로그', 'scraper_background': '스크래퍼 백그라운드 로그',
        'output': '스크래퍼 출력 로그', 'ls_fix_background': 'LS Fix 백그라운드 로그',
    }
    return next((description for pattern, description in descriptions.items() if pattern in name), None)


def is_archived(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in ('.gz', '.zip', '.bz2', '.tar', '.xz'))
