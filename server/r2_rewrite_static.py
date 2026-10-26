#!/usr/bin/env python3
"""改写 dist-static HTML 文件中的静态资源引用为 R2 URL。"""
import os, json, re

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dist-static')
R2 = "https://pub-2c4d70b54401408980230857bdbfcec3.r2.dev/static"

with open(os.path.join(DIST, '.r2-static-mapping.json')) as f:
    mapping = json.load(f)

# 所有需要替换的 (旧前缀, 新URL)
RULES = [
    (re.compile(r'href="/css/style\.css(?:\?[^"]*)?"'),   f'href="{R2}/css/style.css"'),
    (re.compile(r'href="/js/main-dynamic\.js(?:\?[^"]*)?"'), f'src="{R2}/js/main-dynamic.js"'),
    (re.compile(r'href="/js/config\.js(?:\?[^"]*)?"'),    f'src="{R2}/js/config.js"'),
    (re.compile(r'src="/js/main-dynamic\.js(?:\?[^"]*)?"'), f'src="{R2}/js/main-dynamic.js"'),
    (re.compile(r'src="/js/config\.js(?:\?[^"]*)?"'),     f'src="{R2}/js/config.js"'),
    (re.compile(r'src="/js/vcard\.js(?:\?[^"]*)?"'),      f'src="{R2}/js/vcard.js"'),
    (re.compile(r'src="/js/wechat-jssdk\.js(?:\?[^"]*)?"'), f'src="{R2}/js/wechat-jssdk.js"'),
    (re.compile(r'href="/favicon-192\.png(?:\?[^"]*)?"'), f'href="{R2}/favicon-192.png"'),
    (re.compile(r'href="/favicon-512\.png(?:\?[^"]*)?"'), f'href="{R2}/favicon-512.png"'),
    (re.compile(r'href="/manifest\.json(?:\?[^"]*)?"'),   f'href="{R2}/manifest.json"'),
    (re.compile(r'href="/nav\.html(?:\?[^"]*)?"'),        f'href="{R2}/nav.html"'),
]

count = 0
for root, dirs, files in os.walk(DIST):
    for fn in files:
        if not fn.endswith('.html'):
            continue
        path = os.path.join(root, fn)
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        original = html
        for pat, repl in RULES:
            html = pat.sub(repl, html)
        if html != original:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html)
            count += 1
            print(f"  Rewritten: {os.path.relpath(path, DIST)}")

print(f"\nDone: {count} HTML files rewritten")
