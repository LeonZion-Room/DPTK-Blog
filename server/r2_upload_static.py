#!/usr/bin/env python3
"""上传 dist-static 中的 CSS/JS/favicon 等静态资源到 R2 static/ 目录。"""
import os, sys, json, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import boto3
    from botocore.config import Config
except ImportError:
    print("请先安装 boto3: pip3 install boto3"); sys.exit(1)

R2_ENDPOINT = "https://52eb8412db1bac1c0de81e7a3551e7b2.r2.cloudflarestorage.com"
R2_BUCKET = "wechat-card-media"
R2_KEY = "4fb270ab8c95531506b87fd834983fe4"
R2_SECRET = "6c1be504375c941ed7ca0a75c7699f3a4ba905c575edeac204424ff55533a3b1"
PUBLIC_BASE = "https://pub-2c4d70b54401408980230857bdbfcec3.r2.dev"

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dist-static')

# 要上传的静态资源
STATIC_FILES = [
    "css/style.css",
    "js/config.js",
    "js/main-dynamic.js",
    "js/vcard.js",
    "js/wechat-jssdk.js",
    "favicon-192.png",
    "favicon-512.png",
    "manifest.json",
    "nav.html",
]

s3 = boto3.client('s3',
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_KEY,
    aws_secret_access_key=R2_SECRET,
    config=Config(signature_version='s3v4'),
)

def upload_one(relpath):
    local = os.path.join(DIST, relpath)
    key = "static/" + relpath
    if not os.path.exists(local):
        return f"  SKIP {relpath} (not found)"
    with open(local, 'rb') as f:
        data = f.read()
    ct = "text/css" if relpath.endswith('.css') else \
         "application/javascript" if relpath.endswith('.js') else \
         "image/png" if relpath.endswith('.png') else \
         "application/json" if relpath.endswith('.json') else \
         "text/html" if relpath.endswith('.html') else \
         "application/octet-stream"
    s3.put_object(Bucket=R2_BUCKET, Key=key, Body=data,
                  ContentType=ct, CacheControl='public, max-age=31536000')
    url = f"{PUBLIC_BASE}/{key}"
    return f"  OK {relpath} -> {url} ({len(data)} bytes)"

mapping = {}
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {pool.submit(upload_one, f): f for f in STATIC_FILES}
    for fut in as_completed(futures):
        rel = futures[fut]
        result = fut.result()
        print(result)
        if result.startswith("  OK"):
            url = result.split(" -> ")[1].split(" (")[0]
            mapping[rel] = url

# 保存映射
map_path = os.path.join(DIST, '.r2-static-mapping.json')
with open(map_path, 'w') as f:
    json.dump(mapping, f, indent=2, ensure_ascii=False)
print(f"\nMapping saved to {map_path}")
print(f"Uploaded: {len(mapping)} files")
