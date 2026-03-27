---
description: "代码审计: src/classin_downloader"
status: completed
created_at: 2026-03-27T15:30:00
updated_at: 2026-03-27T16:00:00
archived_at: null
---

# 代码审计: src/classin_downloader

## 健康度: C (69/100)

| 维度 | 评分 | 说明 |
|------|------|------|
| 逻辑正确性 | 61 | 并发调度逻辑缺陷、确认流程条件反转、异常静默吞掉 |
| 安全性 | 73 | 登录态校验薄弱、URL scheme 未验证 |
| 性能 | 58 | 视频提取串行 + 大量固定等待，是主要瓶颈 |
| 架构 | 83 | 小工具架构合理，少量职责边界模糊 |

**统计：**
- 扫描文件数：8
- 发现问题数：22（critical: 0, high: 6, medium: 11, low: 5）
- 过滤低置信度：2 个

**修复统计：**
- fixed: 16
- wont_fix: 5
- deferred: 1

## 发现的问题

### High

---

severity: high
confidence: 92
status: fixed
file: src/classin_downloader/downloader.py
line: 126
issue: as_completed 循环批量收集完成项后才调用 submit_next，并发补充严重滞后
detail: |
  外层 `for fut in as_completed(futures):` 会把当前所有已完成的 future 全部迭代完，`submit_next()` 只在整批清空后调用一次。当多个任务几乎同时完成时，线程池在此期间空闲，实际并发度周期性跌至 0。逻辑 + 性能双维度命中。
suggestion: |
  简化为单层 as_completed，每完成一个立即补充：
  ```python
  all_futures = {}
  for v in videos[:max_concurrent]:
      # ... submit initial batch
  for fut in as_completed(all_futures):
      v = all_futures.pop(fut)
      # ... handle result
      if video_queue:
          next_v = video_queue.popleft()
          # ... submit next
  ```
blast_radius: |
  被 1 处调用：
  - app.py:144 (download_all)

---

severity: high
confidence: 92
status: fixed
file: src/classin_downloader/extractor.py
line: 68
issue: 固定轮询等待最多 20 秒/课节（5s LIVE store + 15s 视频源），可用 wait_for_function 替代
detail: |
  get_video_url 内两段 `for _ in range(N): await page.wait_for_timeout(1000)` 串行阻塞。对 30+ 课节累积大量无效等待。Playwright 原生 wait_for_function 可事件驱动替代。
suggestion: |
  ```python
  await page.wait_for_function('!!window.LIVE && !!window.LIVE.$store', timeout=5000)
  ```
  视频源等待同理，设合理 timeout 后 catch TimeoutError 返回空列表。
blast_radius: |
  被 1 处调用：
  - extractor.py:162 (extract_all 循环内)

---

severity: high
confidence: 91
status: fixed
file: src/classin_downloader/extractor.py
line: 146
issue: 每个课程页面导航后无条件 wait_for_timeout(2000)，N 课程浪费 2N 秒
detail: |
  extract_all 在 goto 后固定 2 秒等待。后续 get_lesson_list 通过 fetch API 读数据，不依赖页面完全渲染，此等待无必要。
suggestion: |
  移除固定 sleep，改为 `wait_for_function` 检测 `window.isLogin` 就绪，或直接使用 `wait_until='networkidle'`。
blast_radius: |
  被 1 处调用：
  - app.py:90 (run_extract)

---

severity: high
confidence: 90
status: fixed
file: src/classin_downloader/app.py
line: 134
issue: 确认下载的条件判断逻辑反转，输入 'n' 进入自定义目录而非取消
detail: |
  `if confirm and confirm != 'y':` 含义：输入非空且非 y → 询问自定义目录。用户输入 'n'（表达拒绝）会走入自定义目录分支而非取消，与 `[Y/n]` 的通用语义不符。
suggestion: |
  ```python
  if confirm and confirm != 'y':
      return  # 非 y 直接取消
  ```
  若要保留自定义目录功能，应改为独立选项提示。
blast_radius: |
  交互入口，仅 app.py:run() 内使用

---

severity: high
confidence: 88
status: deferred
deferred_reason: 需要重构为多 page 并发提取，涉及 create_browser_context/extract_all/app.py 编排层的架构变更，风险较高，作为后续优化项
file: src/classin_downloader/extractor.py
line: 137
issue: 所有课节视频 URL 提取完全串行，单 page 逐个处理
detail: |
  extract_all 对每个课节顺序调用 get_video_url，每次 goto + 最多 20 秒轮询。N 课节总时间 O(N×20s)。下载层已做并发，提取层是整体流程的主要瓶颈。
suggestion: |
  打开多个 page（如 3 个），用 asyncio.Semaphore 并发提取多课节。
blast_radius: |
  被 1 处调用：
  - app.py:90 (run_extract)

---

severity: high
confidence: 85
status: fixed
file: src/classin_downloader/auth.py
line: 13
issue: is_logged_in() 仅凭 auth_state.json 文件存在判断，无内容校验
detail: |
  空文件、损坏 JSON、或无 cookies 的文件都会令 is_logged_in() 返回 True，跳过登录流程。后续 create_browser_context 以无效 storage_state 启动，直到 extractor 检测到未登录才报错，用户体验差。
suggestion: |
  ```python
  def is_logged_in() -> bool:
      if not AUTH_FILE.exists():
          return False
      try:
          data = json.loads(AUTH_FILE.read_text(encoding='utf-8'))
          return bool(data.get('cookies'))
      except (json.JSONDecodeError, OSError):
          return False
  ```
blast_radius: |
  被 1 处调用：
  - app.py:107

### Medium

---

severity: medium
confidence: 90
status: fixed
file: src/classin_downloader/downloader.py
line: 116
issue: video_queue.pop(0) 在列表头部删除，时间复杂度 O(N)
detail: |
  submit_next 循环中反复 pop(0)，每次移动整个列表。100+ 课节时产生不必要的开销。
suggestion: |
  ```python
  from collections import deque
  video_queue = deque(videos)
  # ...
  v = video_queue.popleft()  # O(1)
  ```

---

severity: medium
confidence: 88
status: fixed
file: src/classin_downloader/downloader.py
line: 106
issue: task_ids 以文件名为 key，同名课节发生 key 冲突导致进度条混乱
detail: |
  若两个课节经 sanitize_filename 后文件名相同，后者覆盖前者的 task_id，进度跟踪错乱。
suggestion: |
  改用枚举索引或 `id(v)` 作为 key：
  ```python
  task_ids = {}
  for i, v in enumerate(videos):
      tid = progress.add_task(...)
      task_ids[i] = tid
  ```

---

severity: medium
confidence: 88
status: fixed
file: src/classin_downloader/downloader.py
line: 47
issue: HTTP 下载未校验 URL scheme，接受任意协议
detail: |
  video.url 来自 page.evaluate 的 JS 执行结果。若页面被篡改返回 `file://` 等非 HTTPS URL，urllib 会照常执行，可能读取本地文件。
suggestion: |
  ```python
  if not video.url.startswith('https://'):
      console.print(f"  [yellow]跳过非 HTTPS URL: {video.filename}[/]")
      return False
  ```

---

severity: medium
confidence: 85
status: fixed
file: src/classin_downloader/extractor.py
line: 64
issue: page.goto 异常被裸 except 吞掉，后续在错误页面执行 evaluate 可能读取残留数据
detail: |
  goto 超时后页面状态不确定，`window.LIVE.$store` 可能仍是上一个 lesson 的状态，导致错误的视频 URL 被关联到当前课节名称。
suggestion: |
  ```python
  try:
      await page.goto(url, wait_until='load', timeout=60000)
  except Exception as e:
      console.print(f" [red]页面加载失败: {e}[/]")
      return []
  ```

---

severity: medium
confidence: 85
status: wont_fix
wont_fix_reason: 小型 CLI 工具，VideoInfo 是唯一跨模块的 dataclass，拆分到 models.py 增加文件但不减少实际维护负担
file: src/classin_downloader/downloader.py
line: 13
issue: downloader 直接导入 extractor 的 VideoInfo，形成跨层耦合
detail: |
  下载层直接依赖提取层的数据结构。VideoInfo 字段变更时两个模块必须同步修改。
suggestion: |
  将 VideoInfo 移到 config.py 或新建 models.py，两层均依赖共享模型而非互相依赖。

---

severity: medium
confidence: 82
status: wont_fix
wont_fix_reason: vodSourcesClassroom 分支无法提供 size（JS 侧硬编码 '0'），HEAD fallback 是已下载文件校验的唯一手段
file: src/classin_downloader/downloader.py
line: 32
issue: 已完成文件检测时发起额外 HEAD 请求，断点续传场景大量阻塞
detail: |
  当 video.size 为 0 且文件已存在时，_download_one 发起 HEAD 请求获取远端大小。批量重跑时每个文件都触发网络请求。
suggestion: |
  确保提取阶段 VideoInfo.size 尽可能非零（Vuex store 的 `f.Size` 已有数据），下载时仅在 size 为 0 时 fallback HEAD。

---

severity: medium
confidence: 82
status: fixed
file: src/classin_downloader/app.py
line: 92
issue: auth_state 持久化逻辑散落在 app.py，违反 auth 模块单一职责
detail: |
  `context.storage_state(path=str(AUTH_FILE))` 在 app.py:92 和 auth.py:53 两处出现。app.py 需要了解 AUTH_FILE 路径才能完成保存，职责外溢。
suggestion: |
  在 auth.py 中增加 `save_auth_state(context)` 封装保存逻辑，app.py 改为调用该函数。

---

severity: medium
confidence: 82
status: fixed
file: src/classin_downloader/extractor.py
line: 127
issue: int() 转换 JS 返回的 size/duration，空字符串时 ValueError 被静默吞掉
detail: |
  `int(vf.get('size', 0))` 若 JS 返回空字符串 `''`，抛 ValueError，被第 131 行 `except Exception: pass` 吞掉，整个课节提取静默失败。
suggestion: |
  ```python
  size=int(vf.get('size') or 0),
  duration=int(vf.get('duration') or 0),
  ```

---

severity: medium
confidence: 82
status: fixed
file: src/classin_downloader/app.py
line: 135
issue: 用户输入的自定义目录路径未做任何验证
detail: |
  Path(custom) 接受任意字符串，mkdir(parents=True) 会尝试创建。本地 CLI 场景风险有限，但可能意外写入敏感位置。
suggestion: |
  至少提示用户即将创建的目录路径并要求确认。

---

severity: medium
confidence: 80
status: fixed
file: src/classin_downloader/downloader.py
line: 27
issue: sanitize_filename 未防御 .. 序列的路径穿越
detail: |
  当前实现因 `/` `\` 被替换而实际安全，但若未来修改 sanitize 逻辑，`filepath = output_dir / video.filename` 存在穿越风险。
suggestion: |
  增加 `name = name.replace('..', '')` 或使用 `Path(video.filename).name` 取最终文件名。

---

severity: medium
confidence: 78
status: wont_fix
wont_fix_reason: 小工具的合理简化，审查报告自身认可此做法。Rich 已是项目核心依赖，分离收益极低
file: src/classin_downloader/extractor.py
line: 142
issue: extract_all 直接向 console 输出进度，UI 关注点侵入业务逻辑层
detail: |
  extractor.py 多处调用 console.print()。若需要在无 terminal 环境（测试、GUI）使用提取功能，必须连带 Rich 依赖。progress_callback 已预留但仅传数字。
suggestion: |
  扩展 progress_callback 传递文本消息，由 app.py 决定渲染方式。或接受现状作为小工具的合理简化。

### Low

---

severity: low
confidence: 85
status: fixed
file: src/classin_downloader/auth.py
line: 65
issue: create_browser_context 的 Chrome fallback 无异常处理，Edge/Chrome 均缺失时裸异常
detail: |
  login_interactive 中有友好提示，但 create_browser_context 没有，用户在提取阶段看到裸 Playwright 栈。
suggestion: |
  外层加 try/except，打印友好错误信息后 raise。

---

severity: low
confidence: 78
status: fixed
file: src/classin_downloader/app.py
line: 67
issue: total_size 累加时部分 size=0 导致总大小低估但无提示
detail: |
  若部分视频 size 为 0（如 vodSourcesClassroom 分支），total_gb 低估实际总大小，用户无法得知数据不完整。
suggestion: |
  统计时若存在 size=0 的条目，在汇总行旁注明"（部分未知）"。

---

severity: low
confidence: 78
status: wont_fix
wont_fix_reason: 登录是低频一次性操作，1s 响应延迟完全可接受，改 wait_for_function 需要调整超时检测逻辑
file: src/classin_downloader/auth.py
line: 41
issue: 登录检测轮询间隔固定 1 秒，用户完成登录后最多延迟 1 秒
detail: |
  wait_for_timeout(1000) 固定间隔。Playwright 的 wait_for_function 可更快响应。
suggestion: |
  改为 `page.wait_for_function("typeof window.isLogin === 'function' && window.isLogin()", timeout=300000)`，一次调用替代整个循环。

---

severity: low
confidence: 78
status: wont_fix
wont_fix_reason: Windows ACL 操作复杂且平台特定，文件位于用户 app 目录下不是共享路径，风险极低
file: src/classin_downloader/auth.py
line: 53
issue: auth_state.json 明文存储完整 cookie，文件权限未限制
detail: |
  Playwright storage_state 包含所有 cookie/localStorage，等价于登录凭据。默认文件权限下同机器其他用户可访问。
suggestion: |
  写入后设置文件权限为仅当前用户可读，或至少提示用户该文件敏感。

---

severity: low
confidence: 76
status: fixed
file: src/classin_downloader/app.py
line: 138
issue: __import__('pathlib') 动态导入标准库，规避显式 import
detail: |
  反常写法，迷惑代码阅读者和静态分析工具，无实际收益。
suggestion: |
  顶部 `from pathlib import Path`，此处改为 `output_dir = Path(custom)`。

## 低置信度附录

以下问题置信度 < 75，可能是误报，供参考：

---

severity: low
confidence: 72
status: wont_fix
wont_fix_reason: 本地 CLI 工具，lesson_id 来自 ClassIn 官方 API 响应，不经过不可信网络
file: src/classin_downloader/extractor.py
line: 60
issue: lesson_id 来自 API 响应直接拼入 URL，未做格式校验
detail: |
  若 API 被中间人篡改返回特殊字符的 lesson_id，可能导致 URL 行为异常。本地工具场景实际危害极低。
suggestion: |
  对 lesson_id 做 `re.match(r'^[0-9]+$')` 格式断言。

---

severity: low
confidence: 72
status: fixed
file: src/classin_downloader/auth.py
line: 16
issue: login_interactive 默认参数硬编码真实 courseKey
detail: |
  默认值 `'0d75324578d7a17a'` 对其他用户无效。app.py 调用时始终传入实际 key，该默认值从未被正确使用。
suggestion: |
  移除默认值，强制调用方传参。
