import sys
from pathlib import Path


def get_app_dir() -> Path:
    """exe 所在目录（开发时为项目根目录）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


APP_DIR = get_app_dir()
AUTH_FILE = APP_DIR / 'auth_state.json'
DEFAULT_OUTPUT = APP_DIR / 'videos'
COURSES_FILE = APP_DIR / 'courses.txt'
