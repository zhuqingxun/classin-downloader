"""多文件并发下载器：断点续传 + 进度显示"""
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    DownloadColumn, TransferSpeedColumn, TimeRemainingColumn,
)

from .extractor import VideoInfo

console = Console()
_cancel = Event()


def _get_remote_size(url: str) -> int:
    """HEAD 请求获取文件大小"""
    req = urllib.request.Request(url, method='HEAD')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return int(resp.headers.get('Content-Length', 0))


def _download_one(video: VideoInfo, output_dir: Path, progress, task_id) -> bool:
    """下载单个文件，支持断点续传"""
    if not video.url.startswith('https://'):
        console.print(f"  [yellow]跳过非 HTTPS URL: {video.filename}[/]")
        return False

    filepath = output_dir / Path(video.filename).name
    part_path = filepath.with_suffix(filepath.suffix + '.part')

    # 已完成的跳过
    if filepath.exists():
        remote_size = video.size or _get_remote_size(video.url)
        if remote_size and filepath.stat().st_size >= remote_size:
            progress.update(task_id, total=remote_size, completed=remote_size)
            return True

    # 断点续传：检查 .part 文件
    start_byte = 0
    if part_path.exists():
        start_byte = part_path.stat().st_size

    req = urllib.request.Request(video.url)
    if start_byte > 0:
        req.add_header('Range', f'bytes={start_byte}-')

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # 服务器返回 200 说明不支持断点或重新开始
            if resp.status == 200 and start_byte > 0:
                start_byte = 0

            total = int(resp.headers.get('Content-Length', 0))
            if resp.status == 206:
                total += start_byte
            progress.update(task_id, total=total, completed=start_byte)

            mode = 'ab' if start_byte > 0 else 'wb'
            downloaded = start_byte
            with open(part_path, mode) as f:
                while True:
                    if _cancel.is_set():
                        return False
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update(task_id, completed=downloaded)

        # 下载完成，重命名
        if filepath.exists():
            filepath.unlink()
        part_path.rename(filepath)
        return True

    except Exception as e:
        progress.console.print(f"  [red]下载失败: {video.filename} - {e}[/]")
        return False


def download_all(videos: list[VideoInfo], output_dir: Path, max_concurrent: int = 3) -> tuple[int, int]:
    """批量下载所有视频，返回 (成功数, 失败数)"""
    _cancel.clear()
    output_dir.mkdir(parents=True, exist_ok=True)

    success = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[filename]}", justify="left"),
        BarColumn(bar_width=25),
        "[progress.percentage]{task.percentage:>3.0f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:

        # 创建所有任务的进度条
        task_ids = {}
        for i, v in enumerate(videos):
            tid = progress.add_task(
                "download",
                filename=v.filename[:40],
                total=v.size or None,
                visible=False,
            )
            task_ids[i] = tid

        # 并发下载
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {}
            video_queue = deque(range(len(videos)))

            def submit_next():
                while video_queue and len(futures) < max_concurrent:
                    idx = video_queue.popleft()
                    v = videos[idx]
                    tid = task_ids[idx]
                    progress.update(tid, visible=True)
                    fut = executor.submit(_download_one, v, output_dir, progress, tid)
                    futures[fut] = v

            submit_next()

            try:
                while futures:
                    for fut in as_completed(futures):
                        futures.pop(fut)
                        try:
                            if fut.result():
                                success += 1
                            else:
                                failed += 1
                        except Exception:
                            failed += 1
                        submit_next()
                        break
            except KeyboardInterrupt:
                _cancel.set()
                progress.console.print(
                    '\n[yellow]正在停止下载...已下载的部分已保存（支持断点续传）[/]')
                video_queue.clear()
                executor.shutdown(wait=True, cancel_futures=True)

    return success, failed
