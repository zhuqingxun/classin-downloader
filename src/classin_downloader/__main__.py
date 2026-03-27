import sys

if getattr(sys, 'frozen', False):
    print('ClassIn 视频下载器 加载中...')

from classin_downloader.app import main

if __name__ == '__main__':
    main()
