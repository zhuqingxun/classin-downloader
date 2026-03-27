"""自动更新：检查 GitHub Release 新版本并替换 exe"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from rich.console import Console
from rich.progress import (
    Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TextColumn,
)

from . import __version__

console = Console()

GITHUB_API = 'https://api.github.com/repos/zhuqingxun/classin-downloader/releases/latest'
EXE_ASSET_NAME = 'ClassIn\u89c6\u9891\u4e0b\u8f7d\u5668.exe'


def _parse_version(tag: str) -> tuple[int, ...]:
    return tuple(int(x) for x in tag.lstrip('v').split('.'))


def check_update() -> dict | None:
    """检查新版本。返回 {version, url, size} 或 None"""
    try:
        req = urllib.request.Request(GITHUB_API)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None

    tag = data.get('tag_name', '')
    try:
        if _parse_version(tag) <= _parse_version(__version__):
            return None
    except (ValueError, AttributeError):
        return None

    for asset in data.get('assets', []):
        if asset['name'] == EXE_ASSET_NAME:
            return {
                'version': tag,
                'url': asset['browser_download_url'],
                'size': asset['size'],
            }
    return None


def do_update(url: str, version: str) -> bool:
    """下载新版本并安排替换当前 exe"""
    if not getattr(sys, 'frozen', False):
        console.print('[yellow]开发模式下不支持自动更新[/]')
        return False

    exe_path = Path(sys.executable)
    update_path = exe_path.parent / (exe_path.stem + '.update.exe')

    # 清理上次残留
    if update_path.exists():
        update_path.unlink()

    # 下载新版本
    console.print(f'正在下载 {version}...')
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get('Content-Length', 0))
            with Progress(
                TextColumn("[bold blue]更新"),
                BarColumn(bar_width=30),
                DownloadColumn(),
                TransferSpeedColumn(),
                console=console,
            ) as progress:
                tid = progress.add_task("update", total=total or None)
                with open(update_path, 'wb') as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        progress.update(tid, advance=len(chunk))
    except Exception as e:
        console.print(f'[red]下载失败: {e}[/]')
        if update_path.exists():
            update_path.unlink()
        return False

    # 写替换脚本：等待当前进程退出后替换 exe
    bat_path = exe_path.parent / '_update.bat'
    pid = os.getpid()
    bat_content = f'''@echo off
:wait
timeout /t 1 /nobreak > nul 2>&1
tasklist /fi "PID eq {pid}" 2>nul | find /i "{pid}" >nul 2>&1
if not errorlevel 1 goto wait
move /Y "{exe_path}" "{exe_path}.old" >nul 2>&1
move /Y "{update_path}" "{exe_path}" >nul 2>&1
del /f "{exe_path}.old" >nul 2>&1
del /f "%~f0"
'''
    bat_path.write_text(bat_content, encoding='gbk')

    subprocess.Popen(
        ['cmd', '/c', str(bat_path)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )

    console.print(f'[bold green]更新下载完成！程序退出后将自动替换为 {version}。[/]')
    return True
