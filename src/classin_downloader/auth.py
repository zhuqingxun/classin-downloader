"""登录态管理：手动登录 + storage_state 持久化"""
import asyncio

from playwright.async_api import async_playwright
from rich.console import Console

from .config import AUTH_FILE

console = Console()


def is_logged_in() -> bool:
    return AUTH_FILE.exists()


async def login_interactive(course_key: str = '0d75324578d7a17a'):
    """打开浏览器让用户手动登录，自动检测登录成功后保存"""
    console.print('\n[bold yellow]需要登录 ClassIn[/]')
    console.print('即将打开浏览器，请在浏览器中完成登录。')
    console.print('登录成功后脚本会自动继续。\n')

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False, channel='msedge')
        except Exception:
            try:
                browser = await p.chromium.launch(headless=False, channel='chrome')
            except Exception:
                console.print('[bold red]错误: 未找到 Edge 或 Chrome 浏览器[/]')
                console.print('请安装 Microsoft Edge 后重试。')
                return False

        context = await browser.new_context()
        page = await context.new_page()

        url = f'https://live.eeo.cn/pc.html?courseKey={course_key}'
        await page.goto(url, wait_until='load', timeout=30000)

        console.print('[dim]等待登录中... (最多等待 5 分钟)[/]')

        for i in range(300):
            await page.wait_for_timeout(1000)
            try:
                logged_in = await page.evaluate(
                    "() => typeof window.isLogin === 'function' ? window.isLogin() : false")
                if logged_in:
                    break
            except Exception:
                pass
        else:
            console.print('[yellow]超时，仍会保存当前状态[/]')

        await context.storage_state(path=str(AUTH_FILE))
        await browser.close()

    console.print('[bold green]登录态已保存[/]\n')
    return True


async def create_browser_context(playwright):
    """创建已登录的浏览器上下文"""
    try:
        browser = await playwright.chromium.launch(headless=False, channel='msedge')
    except Exception:
        browser = await playwright.chromium.launch(headless=False, channel='chrome')

    context = await browser.new_context(storage_state=str(AUTH_FILE))
    return browser, context
