# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyinstaller>=6.0",
#     "playwright>=1.50",
#     "rich>=13.0",
# ]
# ///
"""构建 exe：自动定位 Playwright driver 并打包"""
import os
import subprocess
import sys

def main():
    # 定位 playwright driver
    import playwright
    pw_dir = os.path.dirname(playwright.__file__)
    pw_driver = os.path.join(pw_dir, 'driver')

    if not os.path.isdir(pw_driver):
        print(f"错误: 未找到 Playwright driver 目录: {pw_driver}")
        sys.exit(1)

    print(f"Playwright driver: {pw_driver}")
    driver_size_mb = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fns in os.walk(pw_driver)
        for f in fns
    ) / 1e6
    print(f"Driver 大小: {driver_size_mb:.0f} MB")

    sep = os.pathsep  # Windows 用 ;

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--console',
        '--name', 'ClassIn视频下载器',
        f'--add-data={pw_driver}{sep}playwright/driver',
        '--collect-submodules=playwright',
        '--collect-submodules=pyee',
        '--hidden-import=greenlet',
        '--hidden-import=rich',
        '--hidden-import=rich.progress',
        '--hidden-import=rich.console',
        '--hidden-import=rich.table',
        '--hidden-import=rich.panel',
        'src/classin_downloader/__main__.py',
    ]

    print(f"\n运行: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        exe_path = os.path.join('dist', 'ClassIn视频下载器.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / 1e6
            print(f"\n构建成功!")
            print(f"  输出: {os.path.abspath(exe_path)}")
            print(f"  大小: {size_mb:.0f} MB")
        else:
            print("\n构建完成，但未找到输出文件")
    else:
        print(f"\n构建失败 (exit code {result.returncode})")
        sys.exit(1)


if __name__ == '__main__':
    main()
