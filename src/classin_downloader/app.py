"""交互式主程序"""
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .auth import create_browser_context, is_logged_in, login_interactive
from .config import AUTH_FILE, COURSES_FILE, DEFAULT_OUTPUT
from .downloader import download_all
from .extractor import VideoInfo, extract_all, parse_course_keys

console = Console()


def show_banner():
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]ClassIn 视频批量下载器[/] [dim]v{__version__}[/]\n"
        "[dim]私用工具，请勿公开传播[/]",
        border_style="blue",
    ))
    console.print()


def input_course_keys() -> list[str]:
    """获取课程链接：优先读文件，否则交互输入"""
    # 先检查 courses.txt
    if COURSES_FILE.exists():
        lines = COURSES_FILE.read_text(encoding='utf-8').splitlines()
        keys = parse_course_keys(lines)
        if keys:
            console.print(f'[dim]从 {COURSES_FILE.name} 读取到 {len(keys)} 个课程[/]')
            return keys

    console.print('[bold]请输入课程链接[/] (每行一个，空行结束):')
    lines = []
    while True:
        try:
            line = input('> ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        lines.append(line)

    keys = parse_course_keys(lines)
    if not keys:
        console.print('[red]未识别到有效的课程链接[/]')
        console.print('[dim]链接格式: https://live.eeo.cn/pc.html?courseKey=xxxx[/]')
    return keys


def show_video_table(videos: list[VideoInfo]):
    """显示视频列表"""
    table = Table(title="视频列表", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("课节名称", style="cyan", max_width=40)
    table.add_column("大小", justify="right", style="green")
    table.add_column("时长", justify="right")

    total_size = 0
    for i, v in enumerate(videos, 1):
        size_mb = v.size / 1e6 if v.size else 0
        total_size += v.size
        size_str = f"{size_mb:.0f}MB" if size_mb else "未知"
        dur_str = f"{v.duration // 60}分{v.duration % 60}秒" if v.duration else "未知"
        table.add_row(str(i), v.lesson_name, size_str, dur_str)

    console.print(table)
    total_gb = total_size / 1e9
    console.print(f"\n共 [bold]{len(videos)}[/] 个视频", end='')
    if total_gb > 0:
        console.print(f"，预估总大小 [bold green]{total_gb:.1f} GB[/]")
    else:
        console.print()


async def run_extract(course_keys: list[str]) -> list[VideoInfo]:
    """运行提取流程"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        page = await context.new_page()

        try:
            videos = await extract_all(page, course_keys)
        finally:
            await context.storage_state(path=str(AUTH_FILE))
            await browser.close()

    return videos


def run():
    show_banner()

    # Step 1: 获取课程链接
    course_keys = input_course_keys()
    if not course_keys:
        return

    # Step 2: 检查登录
    if not is_logged_in():
        console.print('[yellow]首次使用，需要登录 ClassIn[/]')
        ok = asyncio.run(login_interactive(course_keys[0]))
        if not ok:
            return

    # Step 3: 提取视频 URL
    console.print('\n[bold]开始提取视频地址...[/]')
    try:
        videos = asyncio.run(run_extract(course_keys))
    except Exception as e:
        console.print(f'[bold red]提取失败: {e}[/]')
        console.print('[dim]如果是登录问题，请删除 auth_state.json 后重试[/]')
        return

    if not videos:
        console.print('[yellow]未找到任何视频[/]')
        return

    # Step 4: 确认下载
    show_video_table(videos)

    console.print(f'\n下载到: [bold]{DEFAULT_OUTPUT}[/]')
    try:
        confirm = input('确认开始下载? [Y/n] ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if confirm and confirm != 'y':
        custom = input('输入自定义目录 (或回车取消): ').strip()
        if not custom:
            return
        output_dir = __import__('pathlib').Path(custom)
    else:
        output_dir = DEFAULT_OUTPUT

    # Step 5: 下载
    console.print(f'\n[bold]开始下载 {len(videos)} 个视频...[/]\n')
    success, failed = download_all(videos, output_dir, max_concurrent=3)

    # Step 6: 结果
    console.print(f'\n[bold green]完成![/] 成功: {success}, 失败: {failed}')
    console.print(f'文件保存在: [bold]{output_dir.resolve()}[/]')


def main():
    # Windows 默认 ProactorEventLoop，Playwright 需要它来管理 node.exe 子进程
    # 不要切换为 SelectorEventLoop

    try:
        run()
    except KeyboardInterrupt:
        console.print('\n[dim]已取消[/]')

    # exe 模式下暂停，让用户看到结果
    if getattr(sys, 'frozen', False):
        try:
            input('\n按 Enter 退出...')
        except EOFError:
            pass
