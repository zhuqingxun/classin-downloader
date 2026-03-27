"""视频 URL 提取：Playwright 自动化导航 + Vuex store 读取"""
import re
from dataclasses import dataclass, field

from rich.console import Console

console = Console()


@dataclass
class VideoInfo:
    lesson_name: str
    url: str
    filename: str
    size: int = 0
    duration: int = 0
    course_key: str = ''


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip('. ')
    return name[:200]


def parse_course_keys(lines: list[str]) -> list[str]:
    keys = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.search(r'courseKey=([a-f0-9]+)', line)
        if m:
            keys.append(m.group(1))
    return keys


async def get_lesson_list(page, course_key: str) -> list[dict]:
    result = await page.evaluate("""(courseKey) => {
        const fd = new URLSearchParams();
        fd.append('courseKey', courseKey);
        return fetch('https://dynamic.eeo.cn/saasajax/webcast.ajax.php?action=getLessonList', {
            method: 'POST',
            body: fd,
            credentials: 'include',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        }).then(r => r.json());
    }""", course_key)

    if result.get('error_info', {}).get('errno') != 1:
        return []

    lessons = result.get('data', [])
    return [l for l in lessons if l.get('lessonRecord') == 1 and l.get('lessonStatus') == 1]


async def get_video_url(page, course_key: str, lesson: dict) -> list[VideoInfo]:
    lesson_id = lesson['lessonId']
    lesson_name = lesson['lessonName']
    url = f"https://live.eeo.cn/pc.html?courseKey={course_key}&lessonid={lesson_id}"

    try:
        await page.goto(url, wait_until='load', timeout=60000)
    except Exception:
        pass

    # 等待 LIVE store 初始化
    for _ in range(5):
        await page.wait_for_timeout(1000)
        has_live = await page.evaluate("() => !!window.LIVE && !!window.LIVE.$store")
        if has_live:
            break

    # 触发播放
    await page.evaluate("""() => {
        const btn = document.getElementById('big-play-btn');
        if (btn) btn.click();
        if (typeof videojs !== 'undefined') {
            const p = videojs.getPlayers()['player'];
            if (p) try { p.play(); } catch(e) {}
        }
    }""")

    # 等待视频源
    for _ in range(15):
        await page.wait_for_timeout(1000)
        try:
            data = await page.evaluate("""() => {
                if (window.LIVE && window.LIVE.$store) {
                    const vs = window.LIVE.$store.state.videoSource;
                    if (vs && vs.lessonData && vs.lessonData.fileList) {
                        const files = vs.lessonData.fileList;
                        const result = files.filter(f => f.Status === '2').map(f => ({
                            fileId: f.FileId, duration: f.Duration,
                            size: f.Size,
                            urls: f.Playset ? f.Playset.filter(p => p.Definition === '0').map(p => p.Url) : []
                        }));
                        if (result.length > 0 && result[0].urls.length > 0) return result;
                    }
                    const vod = window.LIVE.$store.state.vodSourcesClassroom;
                    if (vod && vod.length > 0) {
                        return vod.map(v => ({
                            fileId: v.fileId || '', duration: 0, size: '0',
                            urls: v.sources ? v.sources.map(s => s.src) : []
                        }));
                    }
                }
                const v = document.querySelector('video');
                if (v && (v.src || v.currentSrc) && !v.srcObject) {
                    const src = v.src || v.currentSrc;
                    if (src && src.includes('playback'))
                        return [{ fileId: '', duration: 0, size: '0', urls: [src] }];
                }
                return null;
            }""")

            if data:
                videos = []
                for fi, vf in enumerate(data):
                    for url in vf.get('urls', []):
                        suffix = f'_part{fi+1}' if len(data) > 1 else ''
                        videos.append(VideoInfo(
                            lesson_name=lesson_name,
                            url=url,
                            filename=sanitize_filename(f"{lesson_name}{suffix}.mp4"),
                            size=int(vf.get('size', 0)),
                            duration=int(vf.get('duration', 0)),
                            course_key=course_key,
                        ))
                return videos
        except Exception:
            pass

    return []


async def extract_all(page, course_keys: list[str], progress_callback=None) -> list[VideoInfo]:
    """提取所有课程的视频 URL"""
    all_videos = []

    for ci, course_key in enumerate(course_keys):
        console.print(f"\n[bold cyan]课程 {ci+1}/{len(course_keys)}[/] courseKey={course_key}")

        await page.goto(f'https://live.eeo.cn/pc.html?courseKey={course_key}',
                        wait_until='load', timeout=60000)
        await page.wait_for_timeout(2000)

        # 验证登录
        is_login = await page.evaluate(
            "() => typeof window.isLogin === 'function' ? window.isLogin() : false")
        if not is_login:
            console.print('[bold red]登录态已过期，请重新运行登录[/]')
            return all_videos

        lessons = await get_lesson_list(page, course_key)
        console.print(f"  找到 [green]{len(lessons)}[/] 个有录制的课节")

        for li, lesson in enumerate(lessons):
            name = lesson['lessonName']
            console.print(f"  [{li+1}/{len(lessons)}] {name} ...", end='')

            videos = await get_video_url(page, course_key, lesson)
            if videos:
                all_videos.extend(videos)
                console.print(f" [green]OK[/] ({len(videos)} 个文件)")
            else:
                console.print(f" [yellow]未找到视频[/]")

            if progress_callback:
                progress_callback(ci, li + 1, len(lessons))

    return all_videos
