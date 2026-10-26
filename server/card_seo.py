"""
card_seo.py - 微信名片自有 SEO 模块（由名片自身数据驱动，不受 Leon-Control 控制）

功能:
1. 从 card_config.json 的 basicInfo 与页面分享信息生成 SEO meta
2. 提供 seo_meta() 供模板输出完整 meta 标签
3. 保留 robots.txt / sitemap.xml 路由
4. 不提供远程 /api/site-config 接口（Leon-Control 无法再控制本服务 SEO）
"""

import json
import os
from urllib.parse import urlparse

from flask import request, Response, url_for


def init_card_seo(app, config_loader, port=8000, base_url="http://119.145.17.34"):
    """
    初始化微信名片自有 SEO 模块

    Args:
        app: Flask app 实例
        config_loader: 无参函数，返回名片配置 dict（load_config）
        port: 服务端口
        base_url: 公网基础 URL
    """

    def get_seo_config():
        """从名片配置生成 SEO 配置（basicInfo + 页面分享信息）"""
        try:
            cfg = config_loader()
        except Exception:
            cfg = {}
        basic = cfg.get('basicInfo', {}) or {}
        settings = cfg.get('settings', {}) or {}

        # 默认页面分享信息
        default_page_id = settings.get('defaultPage', 'home')
        share_title = ''
        share_desc = ''
        share_icon = ''
        for page in cfg.get('pages', []):
            if page.get('id') == default_page_id:
                share_title = page.get('share_title', '')
                share_desc = page.get('share_desc', '')
                share_icon = page.get('share_icon', '')
                break

        name = basic.get('name', '') or share_title or '微信名片'
        title = basic.get('title', '') or ''
        company = basic.get('company', '') or ''
        logo = basic.get('logo', '') or share_icon or ''

        seo = {
            'title': name,
            'subtitle': title or company,
            'description': share_desc or f"{name} 的电子名片{(' - ' + company) if company else ''}",
            'keywords': '微信名片,电子名片,' + (name or ''),
            'author': basic.get('name', '') or 'Leon',
            'logo': logo,
            'favicon': '/favicon-192.png',
            'og_image': logo or '/favicon-512.png',
            'theme_color': '#1e64c8',
            'robots': 'index,follow',
            'canonical_url': f"{base_url}:{port}/",
            'language': 'zh-CN',
            'copyright': f"© 2026 {name or 'Leon'}",
            'site_name': name or '微信名片',
            'extra_head': '',
            'share_title': share_title,
            'share_desc': share_desc,
            'share_icon': share_icon,
        }
        return seo

    app.config['SEO_CARD_LOADER'] = config_loader
    app.config['SEO_CARD_PORT'] = port
    app.config['SEO_CARD_BASE_URL'] = base_url

    def _abs(url):
        if not url:
            return ''
        if url.startswith(('http://', 'https://', '//')):
            return url
        base = f"{base_url}:{port}"
        return base + ('' if url.startswith('/') else '/') + url

    def seo_meta(share_title='', share_desc='', share_icon='', page_title=''):
        """输出完整 SEO meta 标签（供模板 {{ seo_meta()|safe }} 调用）

        支持传入当前页面的分享信息（share_title/share_desc/share_icon）覆盖默认配置，
        从而让微信爬虫抓取到正确的分享卡片内容。
        """
        cfg = get_seo_config()
        # 页面级分享参数优先，其次回退到默认页面配置
        title = share_title or page_title or cfg.get('title', '')
        subtitle = '' if (share_title or page_title) else cfg.get('subtitle', '')
        desc = share_desc or cfg.get('description', '')
        icon = share_icon or cfg.get('og_image', '')
        full_title = f"{title} - {subtitle}" if subtitle and subtitle != title else title
        og_image_url = _abs(icon)
        favicon_url = _abs(cfg.get('favicon', ''))
        logo_url = _abs(cfg.get('logo', ''))
        canonical = cfg.get('canonical_url', '')
        lines = []

        lines.append(f'<meta name="description" content="{desc}">')
        lines.append(f'<meta name="keywords" content="{cfg.get("keywords", "")}">')
        lines.append(f'<meta name="author" content="{cfg.get("author", "")}">')
        lines.append(f'<meta name="robots" content="{cfg.get("robots", "index,follow")}">')
        if canonical:
            lines.append(f'<link rel="canonical" href="{canonical}">')
        if favicon_url:
            lines.append(f'<link rel="icon" type="image/png" href="{favicon_url}">')
            lines.append(f'<link rel="apple-touch-icon" href="{favicon_url}">')
        lines.append(f'<meta name="theme-color" content="{cfg.get("theme_color", "#1e64c8")}">')
        lines.append(f'<meta name="language" content="{cfg.get("language", "zh-CN")}">')
        lines.append(f'<meta name="copyright" content="{cfg.get("copyright", "")}">')
        lines.append('<meta name="generator" content="WeChat-Card-SEO">')

        # Open Graph
        lines.append('<meta property="og:type" content="website">')
        lines.append(f'<meta property="og:title" content="{full_title}">')
        lines.append(f'<meta property="og:description" content="{desc}">')
        if canonical:
            lines.append(f'<meta property="og:url" content="{canonical}">')
        if og_image_url:
            lines.append(f'<meta property="og:image" content="{og_image_url}">')
        lines.append(f'<meta property="og:site_name" content="{cfg.get("site_name", "")}">')
        lines.append('<meta property="og:locale" content="zh_CN">')

        # 旧版微信分享（itemprop）
        lines.append(f'<meta itemprop="name" content="{full_title}">')
        lines.append(f'<meta itemprop="description" content="{desc}">')
        if og_image_url:
            lines.append(f'<meta itemprop="image" content="{og_image_url}">')

        # Twitter Card
        lines.append('<meta name="twitter:card" content="summary_large_image">')
        lines.append(f'<meta name="twitter:title" content="{full_title}">')
        lines.append(f'<meta name="twitter:description" content="{desc}">')
        if og_image_url:
            lines.append(f'<meta name="twitter:image" content="{og_image_url}">')

        # JSON-LD
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": full_title,
            "description": desc,
            "url": canonical,
            "author": {"@type": "Person", "name": cfg.get('author', '')},
            "inLanguage": cfg.get('language', 'zh-CN'),
            "operatingSystem": "Web"
        }
        if logo_url:
            json_ld["logo"] = logo_url
        if og_image_url:
            json_ld["image"] = og_image_url
        lines.append(f'<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>')

        if cfg.get('extra_head'):
            lines.append(cfg['extra_head'])

        return '\n    '.join(lines)

    def seo_meta_dynamic(**overrides):
        """动态 SEO meta（可按页面覆盖 title/description/image）"""
        cfg = get_seo_config().copy()
        cfg.update(overrides)
        lines = []
        title = cfg.get('title', '')
        subtitle = cfg.get('subtitle', '')
        full_title = f"{title} - {subtitle}" if subtitle and subtitle != title else title
        og_image_url = _abs(cfg.get('og_image', ''))
        canonical = cfg.get('canonical_url', '')

        lines.append(f'<meta name="description" content="{cfg.get("description", "")}">')
        lines.append(f'<meta name="keywords" content="{cfg.get("keywords", "")}">')
        lines.append(f'<meta name="robots" content="{cfg.get("robots", "index,follow")}">')
        if canonical:
            lines.append(f'<link rel="canonical" href="{canonical}">')
        lines.append('<meta property="og:type" content="website">')
        lines.append(f'<meta property="og:title" content="{full_title}">')
        lines.append(f'<meta property="og:description" content="{cfg.get("description", "")}">')
        if canonical:
            lines.append(f'<meta property="og:url" content="{canonical}">')
        if og_image_url:
            lines.append(f'<meta property="og:image" content="{og_image_url}">')
        lines.append('<meta name="twitter:card" content="summary_large_image">')
        lines.append(f'<meta name="twitter:title" content="{full_title}">')
        lines.append(f'<meta name="twitter:description" content="{cfg.get("description", "")}">')
        if og_image_url:
            lines.append(f'<meta name="twitter:image" content="{og_image_url}">')
        return '\n    '.join(lines)

    # 注册 Jinja2 全局函数
    app.jinja_env.globals['seo_meta'] = seo_meta
    app.jinja_env.globals['seo_meta_dynamic'] = seo_meta_dynamic
    app.jinja_env.globals['seo_config'] = get_seo_config

    @app.context_processor
    def inject_seo():
        return {'seo': get_seo_config()}

    # ==================== SEO 路由（无远程 API） ====================

    @app.route('/robots.txt')
    def card_robots():
        cfg = get_seo_config()
        robots_content = cfg.get('robots', 'index,follow')
        allow = "Allow: /" if "index" in robots_content else "Disallow: /"
        txt = f"User-agent: *\n{allow}\n\nSitemap: {cfg.get('canonical_url', '').rstrip('/')}/sitemap.xml\n"
        return Response(txt, mimetype='text/plain')

    @app.route('/sitemap.xml')
    def card_sitemap():
        cfg = get_seo_config()
        url = cfg.get('canonical_url', '').rstrip('/')
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{url}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
        return Response(xml, mimetype='application/xml')

    return app
