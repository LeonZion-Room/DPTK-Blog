#!/usr/bin/env python3
"""上传 dist-static 中的媒体文件到 Cloudflare R2。
用法: python3 r2_upload.py [--dry-run]

依赖: pip install boto3
"""
import os
import sys
import json
import mimetypes
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.config import Config

# --- R2 配置 ---
R2_ENDPOINT = 'https://52eb8412db1bac1c0de81e7a3551e7b2.r2.cloudflarestorage.com'
R2_ACCESS_KEY = '4fb270ab8c95531506b87fd834983fe4'
R2_SECRET_KEY = '6c1be504375c941ed7ca0a75c7699f3a4ba905c575edeac204424ff55533a3b1'
R2_BUCKET = 'wechat-card-media'
R2_PUBLIC_BASE = 'https://pub-2c4d70b54401408980230857bdbfcec3.r2.dev'

# 本地媒体目录
MEDIA_DIRS = ['uploads', 'pdf', 'view']

# 上传并发数
MAX_WORKERS = 4


def get_s3_client():
    return boto3.client('s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(
            max_pool_connections=MAX_WORKERS,
            retries={'max_attempts': 3, 'mode': 'adaptive'},
        ),
        region_name='auto',
    )


def collect_media_files(dist_static):
    """收集所有需要上传的媒体文件。返回 [(local_path, r2_key, file_size), ...]"""
    files = []
    for subdir in MEDIA_DIRS:
        dirpath = os.path.join(dist_static, subdir)
        if not os.path.isdir(dirpath):
            continue
        for root, _, fnames in os.walk(dirpath):
            for fname in fnames:
                local = os.path.join(root, fname)
                rel = os.path.relpath(local, dist_static)
                r2_key = rel  # uploads/foo.png, pdf/bar.pdf, etc.
                size = os.path.getsize(local)
                files.append((local, r2_key, size))
    return files


def upload_file(s3, local_path, r2_key, dry_run=False):
    """上传单个文件到 R2，返回 (r2_key, ok, error_msg)"""
    if dry_run:
        return (r2_key, True, 'dry-run')
    try:
        content_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        extra = {'ContentType': content_type}
        s3.upload_file(local_path, R2_BUCKET, r2_key, ExtraArgs=extra)
        return (r2_key, True, None)
    except Exception as e:
        return (r2_key, False, str(e))


def main():
    dry_run = '--dry-run' in sys.argv
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_static = os.path.join(project_root, 'dist-static')

    if not os.path.isdir(dist_static):
        print('ERROR: dist-static/ not found at', dist_static)
        sys.exit(1)

    files = collect_media_files(dist_static)
    total_size = sum(f[2] for f in files)
    print(f'Found {len(files)} media files ({total_size / 1024 / 1024:.1f} MB)')

    if not files:
        print('Nothing to upload.')
        return

    s3 = get_s3_client() if not dry_run else None
    uploaded = 0
    failed = 0
    skipped = 0
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for local, key, size in files:
            fut = pool.submit(upload_file, s3, local, key, dry_run)
            futures[fut] = (key, size)

        for fut in as_completed(futures):
            key, size = futures[fut]
            r2_key, ok, err = fut.result()
            if ok:
                if err == 'dry-run':
                    skipped += 1
                    print(f'  [DRY] {r2_key} ({size/1024:.0f}KB)')
                else:
                    uploaded += 1
                    results.append({'r2_key': r2_key, 'r2_url': R2_PUBLIC_BASE + '/' + r2_key})
                    print(f'  OK {r2_key} ({size/1024:.0f}KB)')
            else:
                failed += 1
                print(f'  FAIL {r2_key}: {err}')

    print(f'\nDone: {uploaded} uploaded, {failed} failed, {skipped} dry-run')

    # 保存映射表
    mapping_path = os.path.join(dist_static, '.r2-mapping.json')
    with open(mapping_path, 'w') as f:
        json.dump({
            'public_base': R2_PUBLIC_BASE,
            'bucket': R2_BUCKET,
            'files': results,
        }, f, indent=2, ensure_ascii=False)
    print(f'Mapping saved to {mapping_path}')


if __name__ == '__main__':
    main()
