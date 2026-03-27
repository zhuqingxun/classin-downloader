# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

ClassIn (eeo.cn) 课程视频批量下载工具。通过 Playwright 自动化浏览器提取视频地址，多线程并发下载并支持断点续传。交互式 CLI，同时支持打包为独立 exe 分发。

## 常用命令

```bash
# 安装依赖
uv sync --no-install-project

# 运行（交互式 CLI，需要终端 stdin）
uv run classin-dl

# 构建 exe（PEP 723 脚本，自动安装 pyinstaller）
uv run --script build.py
```

## 架构

流水线式处理：**认证 → 提取 → 下载**，入口在 `app.py:run()`。

- **auth.py** — 登录态管理。首次使用打开浏览器让用户手动登录，通过 Playwright `storage_state()` 持久化到 `auth_state.json`，后续复用。优先尝试 Edge，回退到 Chrome。
- **extractor.py** — 视频地址提取。通过 ClassIn 的 `getLessonList` API 获取课节列表，然后逐课节导航页面，从 `window.LIVE.$store.state.videoSource`（Vuex store）中读取视频文件信息。有三层回退：`videoSource.lessonData.fileList` → `vodSourcesClassroom` → DOM `<video>` 元素。
- **downloader.py** — 多线程并发下载（默认 3 线程），使用 `.part` 临时文件 + HTTP Range 实现断点续传，Rich Progress 显示进度。
- **config.py** — 路径配置，区分 frozen（exe）和开发模式。
- **courses.txt** — 课程链接输入文件，每行一个 `https://live.eeo.cn/pc.html?courseKey=xxx`。

## 关键技术细节

- 浏览器自动化使用 **非 headless** 模式（`headless=False`），因为 ClassIn 需要用户可见的浏览器环境
- 视频提取依赖页面 JS 环境（`window.LIVE.$store`），需等待 Vue/Vuex 初始化完成后才能读取
- Windows 上必须使用 ProactorEventLoop（Playwright 管理 node.exe 子进程需要），不要切换为 SelectorEventLoop
- `build.py` 是 PEP 723 脚本（inline dependencies），必须用 `uv run --script` 执行
