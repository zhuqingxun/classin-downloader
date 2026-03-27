---
title: "视频提取并发化（审计 extractor.py:137）"
type: issue
status: open
priority: high
source: rpiv/validation/code-audit-src-classin-downloader.md#extractor-137
created_at: 2026-03-27T16:00:00
updated_at: 2026-03-27T16:00:00
---

# 视频提取并发化

## 问题现象

extract_all 对所有课节视频 URL 逐个串行提取，每课节 goto + 最多 15s wait_for_function。N 课节总时间 O(N)，是整体流程的主要性能瓶颈。

## 根本原因

当前仅使用单个 Playwright page 逐课节导航，而 Playwright 支持多 page 并发操作。

## 影响范围

- src/classin_downloader/extractor.py (extract_all)
- src/classin_downloader/app.py (run_extract 编排层)

## 已知 Workaround

无。当前已通过 wait_for_function 替代固定 sleep 减少了单课节等待时间，但串行结构未变。

## 已尝试的方案

无

## 参考

- 审计报告：rpiv/validation/code-audit-src-classin-downloader.md
- 建议方案：打开 3 个 page，用 asyncio.Semaphore 并发提取
