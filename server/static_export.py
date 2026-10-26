#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信名片一键导出静态站。
把全部名片页预渲染为 <项目根>/dist-static/，目录可直接推 GitHub，
经 Cloudflare Pages 发布为纯静态站。原站 Flask 保持不动，继续做编辑后台。

原理：名片页由 main-dynamic.js 经 /api/card-config 拉配置渲染。
导出时对每页内嵌该页 config + fetch 拦截垫片，不再请求 /api；
站内跳转 /?page=X 与 /index-dynamic.html?page=X 改写为 /p/X/。
media_local=True 时下载所有媒体到 dist-static，URL 改写为相对路径；
media_local=False 时热链原站（零下载立即可用）。
仅依赖标准库。
"""

import copy
import datetime
import json
import os
import re
import shutil
import urllib.request
import urllib.error

SHIM_TEMPLATE = """<script>
/* WeChat-Card static build: 内嵌配置 + fetch 拦截，无需 /api 后端 */
window.__STATIC_PAGE_ID__ = "__PAGE_ID__";
window.__STATIC_CONFIG__ = __CONFIG_JSON__;
(function() {
  var STATIC = window.__STATIC_CONFIG__;
  var PAGE = window.__STATIC_PAGE_ID__;
  function staticResp(obj) {
    return Promise.resolve(new Response(JSON.stringify(obj), {headers: {'Content-Type': 'application/json'}}));
  }
  var origFetch = window.fetch.bind(window);
  window.fetch = function(url, opts) {
    try {
      var s = String((url && url.url) || url);
      if (s.indexOf('/api/card-config') !== -1) {
        try {
          var u = new URL(s, location.origin);
          var pid = u.searchParams.get('page') || PAGE;
          if (pid === PAGE) return staticResp(STATIC);
          return origFetch('/p/' + pid + '/config.json', opts).then(function(r) {
            if (r.ok) return r;
            return staticResp(STATIC);
          }).catch(function() { return staticResp(STATIC); });
        } catch (e) { return staticResp(STATIC); }
      }
      if (s.indexOf('/api/groups') !== -1) return staticResp({groups: (STATIC.groups || [])});
      if (s.indexOf('/api/wechat-sign') !== -1) return staticResp({});
    } catch (e) {}
    return origFetch(url, opts);
  };
})();
</script>"""

# 从项目根拷贝的静态资源（显式文件清单，不含 .bak）
STATIC_FILES = [
    'css/style.css',
    'js/main-dynamic.js',
    'js/config.js',
    'js/vcard.js',
    'js/wechat-jssdk.js',
    'manifest.json',
    'favicon-192.png',
    'favicon-512.png',
]

# --- 正则 ---
ORIGIN_RE = re.compile(r'https?://119\.145\.17\.34:8000/index-dynamic\.html\?page=([\w\-\.]+)')
ORIGIN_ROOT_RE = re.compile(r'https?://119\.145\.17\.34:8000/\?page=([\w\-\.]+)')
REL_RE = re.compile(r'["\']/index-dynamic\.html\?page=([\w\-\.]+)["\']')
# 旧域名改写：119.145.17.34:8000
_OLD_DOMAIN = re.compile(r'https?://119\.145\.17\.34(:8000)?')
# 任意域名的绝对媒体 URL（uploads/pdf/view 路径，含文件名）
_MEDIA_ABS = re.compile(r'https?://[^/]+/(?:uploads|pdf|view)/[^\s"\'}\),]+')
# SEO canonical / og:url 改写
_SEO_URL_RE = re.compile(r'(?:canonical|og:url)\s+content="https?://[^"]+"')


def rewrite_internal_links(text):
    """站内跳转改写为静态路径 /p/<id>/"""
    text = ORIGIN_RE.sub(r'/p/\1/', text)
    text = ORIGIN_ROOT_RE.sub(r'/p/\1/', text)
    text = REL_RE.sub(r'"/p/\1/"', text)
    return text


def rewrite_media_urls(text, media_origin):
    """把 uploads/pdf/view 资源从旧域名改写到 media_origin（热链模式）"""
    if not media_origin:
        return text
    def _repl(m):
        url = m.group(0)
        # 提取 /uploads/... 或 /pdf/... 路径部分
        path = re.sub(r'^https?://[^/]+', '', url)
        return media_origin.rstrip('/') + path
    return _MEDIA_ABS.sub(_repl, text)


def rewrite_media_to_relative(text):
    """把任意域名的绝对媒体 URL 改写为根相对路径（本地模式）：/uploads/..."""
    def _repl(m):
        url = m.group(0)
        return re.sub(r'^https?://[^/]+', '', url)
    return _MEDIA_ABS.sub(_repl, text)


def absolutize_assets(html):
    """相对资源引用改为根绝对路径，使 /p/<id>/ 子路径页面可用；禁用 SW 注册"""
    html = html.replace('href="css/', 'href="/css/')
    html = html.replace("href='css/", "href='/css/")
    html = html.replace('src="js/', 'src="/js/')
    html = html.replace("src='js/", "src='/js/")
    html = html.replace('href="favicon-', 'href="/favicon-')
    html = html.replace('href="manifest.json"', 'href="/manifest.json"')
    html = re.sub(r'<script>\s*if\s*\(\s*"serviceWorker"[\s\S]*?</script>',
                  '<!-- sw disabled in static build -->', html)
    return html


def rewrite_domain(text, media_origin):
    """把 config/currentDomain 从旧域名改写到 media_origin。"""
    if not media_origin:
        return text
    return _OLD_DOMAIN.sub(media_origin.rstrip('/'), text)


def rewrite_seo_urls(html, media_origin):
    """HTML SEO canonical/og:url 改写到 media_origin，或清空旧域名。"""
    if media_origin is None:
        return html
    if media_origin:
        return _SEO_URL_RE.sub('content="' + media_origin.rstrip('/') + '"', html)
    # media_origin 为空：去掉 canonical/og:url 中的旧域名
    html = re.sub(r'<link[^>]*canonical[^>]*href="[^"]*"[^>]*>', '', html)
    html = re.sub(r'<meta[^>]*property="og:url"[^>]*content="[^"]*"[^>]*>', '', html)
    return html


def inject_shim(html, page_id, config_obj, media_origin=None, media_local=False):
    cfg_json = rewrite_internal_links(json.dumps(config_obj, ensure_ascii=False))
    if media_local:
        cfg_json = rewrite_media_to_relative(cfg_json)
    else:
        cfg_json = rewrite_media_urls(cfg_json, media_origin)
        cfg_json = rewrite_domain(cfg_json, media_origin)
    shim = SHIM_TEMPLATE.replace('__PAGE_ID__', page_id).replace('__CONFIG_JSON__', cfg_json)
    marker = 'src="/js/main-dynamic.js'
    if marker in html:
        html = html.replace(marker, shim + '\n  <script src="/js/main-dynamic.js', 1)
    else:
        html = html.replace('</body>', shim + '\n</body>')
    html = rewrite_internal_links(html)
    if media_local:
        html = rewrite_media_to_relative(html)
        html = rewrite_seo_urls(html, '')  # 清空 SEO canonical/og:url 中的旧域名
        html = _OLD_DOMAIN.sub('', html)  # 清除模板中残留的旧域名引用
    else:
        html = rewrite_media_urls(html, media_origin)
        html = rewrite_seo_urls(html, media_origin)
    return html


def build_page_config(config, page_id, current_domain, resolve_fn=None):
    """复刻 /api/card-config?page=<id> 的返回结构（含 mapping 展开与降级逻辑）。"""
    cfg = copy.deepcopy(config)
    if 'pages' not in cfg:
        cfg['pages'] = []
    page_found = False
    if page_id:
        for page in cfg['pages']:
            if page['id'] == page_id:
                cfg['currentPage'] = page
                page_found = True
                break
        if not page_found:
            fallback_id = cfg.get('settings', {}).get('defaultPage', 'home')
            if fallback_id and fallback_id != page_id:
                for page in cfg['pages']:
                    if page['id'] == fallback_id:
                        cfg['currentPage'] = page
                        page_found = True
                        break
            if not page_found:
                cfg['currentPage'] = {
                    'id': page_id, 'title': page_id, 'groupId': 'default',
                    'sections': [{'type': 'title', 'level': 1,
                                  'title': '页面 %s 待创建' % page_id}],
                    '_placeholder': True,
                }
    else:
        default_page_id = cfg.get('settings', {}).get('defaultPage', 'home')
        for page in cfg['pages']:
            if page['id'] == default_page_id:
                cfg['currentPage'] = page
                break
    if resolve_fn is not None:
        cfg = resolve_fn(cfg)
    cfg['currentDomain'] = current_domain
    return cfg


def _collect_media_urls(config):
    """从 config JSON 中提取所有绝对媒体 URL（uploads/pdf/view）。返回去重列表。"""
    text = json.dumps(config, ensure_ascii=False)
    urls = set()
    for m in _MEDIA_ABS.finditer(text):
        full = m.group(0)
        urls.add(full)
    return sorted(urls)


def _download_file(url, dest, timeout=30):
    """下载单个文件，返回 (ok, error_msg)。"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(data)
        return True, None
    except Exception as e:
        return False, str(e)


def download_media_files(project_root, out_dir, config, source_origin,
                         progress_cb=None):
    """扫描 config 中所有媒体 URL，下载到 dist-static 对应目录。
    source_origin: 下载源（如 http://szdptk.com:8000）。
    返回 (downloaded_count, errors_list)。
    """
    urls = _collect_media_urls(config)
    downloaded = 0
    errors = []
    for url in urls:
        # 把任意域名 URL 替换为 source_origin
        path = re.sub(r'^https?://[^/]+', '', url)
        dest = os.path.join(out_dir, path.lstrip('/'))
        if os.path.exists(dest):
            downloaded += 1
            continue
        ok, err = _download_file(source_origin.rstrip('/') + path, dest)
        if ok:
            downloaded += 1
        else:
            errors.append('%s: %s' % (path, err))
        if progress_cb:
            progress_cb(downloaded, len(urls), path)
    return downloaded, errors


def export_all(render_html_fn, config, resolve_fn, current_domain,
               project_root, out_name='dist-static', media_origin=None,
               media_local=False, media_source=None):
    """导出全部页面。render_html_fn(pid)->str 为服务端渲染好的整页 HTML。
    media_local: True 时下载媒体到本地并改写为相对路径；False 时热链 media_origin。
    media_source: 下载媒体时的源域名（如 http://szdptk.com:8000），默认用 current_domain。
    返回 stats dict: {pages, out_dir, out_rel, bytes, errors}。
    """
    out_dir = os.path.join(project_root, out_name)
    os.makedirs(out_dir, exist_ok=True)
    for d in ('css', 'js', 'p', 'uploads', 'pdf', 'view'):
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)

    errors = []
    for rel in STATIC_FILES:
        src = os.path.join(project_root, rel)
        dst = os.path.join(out_dir, rel)
        try:
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            else:
                errors.append('asset missing: ' + rel)
        except Exception as e:
            errors.append('asset %s: %s' % (rel, e))

    # 本地模式：下载媒体文件
    if media_local:
        dl_src = media_source or current_domain
        dl_count, dl_errors = download_media_files(
            project_root, out_dir, config, dl_src)
        errors.extend(dl_errors)
    else:
        dl_count = 0

    # 构建每页
    pages = config.get('pages', [])
    ok = []
    for p in pages:
        pid = p.get('id')
        try:
            html = render_html_fn(pid)
            cfg_domain = '' if media_local else current_domain
            cfg = build_page_config(config, pid, cfg_domain, resolve_fn)
            html = inject_shim(absolutize_assets(html), pid, cfg,
                               media_origin, media_local)
            pdir = os.path.join(out_dir, 'p', pid)
            os.makedirs(pdir, exist_ok=True)
            with open(os.path.join(pdir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(html)
            cfg_text = rewrite_internal_links(json.dumps(cfg, ensure_ascii=False))
            if media_local:
                cfg_text = rewrite_media_to_relative(cfg_text)
            else:
                cfg_text = rewrite_media_urls(cfg_text, media_origin)
                cfg_text = rewrite_domain(cfg_text, media_origin)
            with open(os.path.join(pdir, 'config.json'), 'w', encoding='utf-8') as f:
                f.write(cfg_text)
            ok.append(pid)
        except Exception as e:
            errors.append('page %s: %s' % (pid, e))

    default_page = (config.get('settings') or {}).get('defaultPage', 'home')
    root_src = default_page if default_page in ok else (ok[0] if ok else None)
    if root_src:
        with open(os.path.join(out_dir, 'p', root_src, 'index.html'),
                  encoding='utf-8') as f:
            root_html = f.read()
        with open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(root_html)

    nav = ['<html><head><meta charset="utf-8"><title>名片导航</title></head>'
           '<body><h1>名片导航</h1><ul>']
    id2title = {p.get('id'): p.get('title', p.get('id')) for p in pages}
    for pid in ok:
        nav.append('<li><a href="/p/%s/">%s (%s)</a></li>'
                   % (pid, id2title.get(pid, pid), pid))
    nav.append('</ul></body></html>')
    with open(os.path.join(out_dir, 'nav.html'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(nav))

    total = 0
    for base, _, files in os.walk(out_dir):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(base, fn))
            except OSError:
                pass
    info = {
        'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'pages': len(ok),
        'default_page': root_src,
        'bytes': total,
        'media_downloaded': dl_count if media_local else 0,
        'errors': errors,
    }
    with open(os.path.join(out_dir, '.export-info.json'), 'w',
              encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return {'pages': len(ok), 'out_dir': out_dir, 'out_rel': out_name,
            'bytes': total, 'errors': errors}


def last_export_info(project_root, out_name='dist-static'):
    fp = os.path.join(project_root, out_name, '.export-info.json')
    if os.path.exists(fp):
        try:
            with open(fp, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}
