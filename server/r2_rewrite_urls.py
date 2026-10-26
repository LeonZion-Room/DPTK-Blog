#!/usr/bin/env python3
"""R2 上传后，改写 dist-static 中所有媒体 URL 从相对路径到 R2 绝对路径。
用法: python3 r2_rewrite_urls.py

配合 r2_upload.py 使用。先上传，再改写。
"""
import os
import re
import json
import glob

R2_PUBLIC_BASE = 'https://pub-2c4d70b54401408980230857bdbfcec3.r2.dev'

# 匹配相对媒体路径（在 JSON 值和 HTML 属性中）
# /uploads/xxx.png, /pdf/xxx.pdf, /view/xxx
_REL_MEDIA_RE = re.compile(r'(?<=")/(uploads/|pdf/|view/)[^\s"\'}\),]+(?=")')


def rewrite_file(filepath, r2_base):
    """改写单个文件中的相对媒体 URL 为 R2 绝对 URL。返回改写数量。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return 0

    def _repl(m):
        path = m.group(0)  # /uploads/xxx.png
        return r2_base.rstrip('/') + path

    new_content = _REL_MEDIA_RE.sub(_repl, content)
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return len(_REL_MEDIA_RE.findall(content))
    return 0


def main():
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_static = os.path.join(project_root, 'dist-static')

    if not os.path.isdir(dist_static):
        print('ERROR: dist-static/ not found')
        sys.exit(1)

    total_rewrites = 0
    files_changed = 0

    # 改写所有 HTML 和 JSON 文件
    for pattern in ['**/*.html', '**/*.json']:
        for filepath in glob.glob(os.path.join(dist_static, pattern), recursive=True):
            if '.export-info' in filepath or '.r2-mapping' in filepath:
                continue
            count = rewrite_file(filepath, R2_PUBLIC_BASE)
            if count > 0:
                total_rewrites += count
                files_changed += 1
                rel = os.path.relpath(filepath, dist_static)
                print(f'  {rel}: {count} URLs rewritten')

    print(f'\nDone: {total_rewrites} URLs in {files_changed} files')


if __name__ == '__main__':
    main()
