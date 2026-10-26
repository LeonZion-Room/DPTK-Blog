"""
seo_helper.py - 公共 SEO / 对外展示信息注入模块

使用方法（在各项目 app.py 中添加）:
    from seo_helper import init_seo
    init_seo(app, project_id="1", project_name="微信名片", port=8000)

功能:
1. 自动加载 / 保存 site_config.json（项目对外展示信息）
2. 通过 context_processor 向所有模板注入 seo 变量
3. 提供 GET/PUT /api/site-config 接口供 Leon-Control 远程管理
4. 提供 /robots.txt 和 /sitemap.xml 路由提升搜索引擎收录
5. 提供 seo_meta() 函数，模板中调用 {{ seo_meta() }} 输出完整 meta 标签
"""

import os
import json
from urllib.parse import urlparse
from functools import wraps
from flask import request, jsonify, current_app, Response

# 默认配置模板
DEFAULT_CONFIG = {
    "title": "",
    "subtitle": "",
    "description": "",
    "keywords": "",
    "author": "Leon",
    "logo": "/static/logo.png",
    "favicon": "/static/favicon.png",
    "og_image": "/static/og-image.png",
    "theme_color": "#1677ff",
    "robots": "index,follow",
    "canonical_url": "",
    "language": "zh-CN",
    "copyright": "© 2026 Leon",
    "site_name": "Leon Studio",
    "extra_head": ""
}

# API 鉴权 token
API_TOKEN = "wswwsw1234"

# Leon-Control 管理地址（用于生成 sitemap 等）
LEON_CONTROL_URL = "http://119.145.17.34:5000"


def _require_token(f):
    """API token 鉴权装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.args.get('token') or request.headers.get('X-Site-Token')
        if token == API_TOKEN:
            return f(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    return decorated


def _load_config(config_path):
    """加载 site_config.json，不存在则返回默认配置"""
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            # 合并默认值（保证字段完整）
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
            return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def _save_config(config_path, config):
    """保存配置到 site_config.json"""
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def init_seo(app, project_id, project_name, port, base_url="http://119.145.17.34"):
    """
    初始化 SEO 模块

    Args:
        app: Flask app 实例
        project_id: Leon-Control 中的项目 ID
        project_name: 项目名称
        port: 项目端口
        base_url: 公网基础 URL
    """
    # 配置文件路径：app.root_path（app.py 所在目录）/ site_config.json
    config_path = os.path.join(app.root_path, 'site_config.json')

    # 如果配置文件不存在，创建默认配置
    if not os.path.exists(config_path):
        default_cfg = DEFAULT_CONFIG.copy()
        default_cfg['title'] = project_name
        default_cfg['description'] = f"{project_name} - Leon Studio 出品"
        default_cfg['canonical_url'] = f"{base_url}:{port}/"
        default_cfg['keywords'] = project_name
        _save_config(config_path, default_cfg)

    # 存储 meta 信息到 app config
    app.config['SEO_CONFIG_PATH'] = config_path
    app.config['SEO_PROJECT_ID'] = project_id
    app.config['SEO_PROJECT_NAME'] = project_name
    app.config['SEO_PORT'] = port
    app.config['SEO_BASE_URL'] = base_url

    def get_seo_config():
        """获取当前 SEO 配置"""
        return _load_config(app.config['SEO_CONFIG_PATH'])

    def seo_meta():
        """Jinja2 全局函数：输出完整 SEO meta 标签 HTML（不含 title，title 由模板通过 seo.title 输出）"""
        cfg = get_seo_config()
        lines = []

        title = cfg.get('title', '')
        subtitle = cfg.get('subtitle', '')
        full_title = f"{title} - {subtitle}" if subtitle else title

        # 辅助函数：把相对路径补全为完整网络 URL
        def _abs(url):
            if not url:
                return ''
            if url.startswith(('http://', 'https://', '//')):
                return url
            # 相对路径：用 canonical_url 的域名部分（scheme://host:port）补全
            canon = cfg.get('canonical_url', '')
            if canon:
                parsed = urlparse(canon)
                base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else canon.rstrip('/')
            else:
                base = f"http://119.145.17.34:{port}"
            return base + ('' if url.startswith('/') else '/') + url

        favicon_url = _abs(cfg.get('favicon', ''))
        logo_url = _abs(cfg.get('logo', ''))
        og_image_url = _abs(cfg.get('og_image', ''))

        lines.append(f'<meta name="description" content="{cfg.get("description", "")}">')
        lines.append(f'<meta name="keywords" content="{cfg.get("keywords", "")}">')
        lines.append(f'<meta name="author" content="{cfg.get("author", "")}">')
        lines.append(f'<meta name="robots" content="{cfg.get("robots", "index,follow")}">')

        if cfg.get('canonical_url'):
            lines.append(f'<link rel="canonical" href="{cfg["canonical_url"]}">')

        if favicon_url:
            lines.append(f'<link rel="icon" type="image/png" href="{favicon_url}">')
            lines.append(f'<link rel="apple-touch-icon" href="{favicon_url}">')

        if cfg.get('theme_color'):
            lines.append(f'<meta name="theme-color" content="{cfg["theme_color"]}">')

        lines.append(f'<meta name="language" content="{cfg.get("language", "zh-CN")}">')
        lines.append(f'<meta name="copyright" content="{cfg.get("copyright", "")}">')
        lines.append(f'<meta name="generator" content="Leon-SEO-Helper">')

        # Open Graph
        lines.append('<meta property="og:type" content="website">')
        lines.append(f'<meta property="og:title" content="{full_title}">')
        lines.append(f'<meta property="og:description" content="{cfg.get("description", "")}">')
        if cfg.get('canonical_url'):
            lines.append(f'<meta property="og:url" content="{cfg["canonical_url"]}">')
        if og_image_url:
            lines.append(f'<meta property="og:image" content="{og_image_url}">')
        lines.append(f'<meta property="og:site_name" content="{cfg.get("site_name", "")}">')
        lines.append(f'<meta property="og:locale" content="zh_CN">')

        # Twitter Card
        lines.append('<meta name="twitter:card" content="summary_large_image">')
        lines.append(f'<meta name="twitter:title" content="{full_title}">')
        lines.append(f'<meta name="twitter:description" content="{cfg.get("description", "")}">')
        if og_image_url:
            lines.append(f'<meta name="twitter:image" content="{og_image_url}">')

        # JSON-LD 结构化数据（利于 AI 和搜索引擎理解）
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": title,
            "description": cfg.get('description', ''),
            "url": cfg.get('canonical_url', ''),
            "author": {
                "@type": "Person",
                "name": cfg.get('author', 'Leon')
            },
            "inLanguage": cfg.get('language', 'zh-CN'),
            "operatingSystem": "Web"
        }
        if logo_url:
            json_ld["logo"] = logo_url
        if og_image_url:
            json_ld["image"] = og_image_url
        lines.append(f'<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>')

        # 额外自定义 head 内容
        if cfg.get('extra_head'):
            lines.append(cfg['extra_head'])

        return '\n    '.join(lines)

    def seo_meta_dynamic(**overrides):
        """Jinja2 全局函数：输出动态 SEO meta 标签（可覆盖 title/description/image/canonical_url 等）
        用法：{{ seo_meta_dynamic(title=item.name, description=item.summary, image=item.cover)|safe }}
        """
        cfg = get_seo_config().copy()
        cfg.update(overrides)
        # 临时替换 get_seo_config 的返回值来复用 seo_meta 逻辑
        # 由于 seo_meta 内部调用 get_seo_config()，这里直接内联生成
        lines = []
        title = cfg.get('title', '')
        subtitle = cfg.get('subtitle', '')
        full_title = f"{title} - {subtitle}" if subtitle and title != subtitle else title

        def _abs(url):
            if not url:
                return ''
            if url.startswith(('http://', 'https://', '//')):
                return url
            canon = cfg.get('canonical_url', '')
            if canon:
                parsed = urlparse(canon)
                base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else canon.rstrip('/')
            else:
                base = f"http://119.145.17.34:{port}"
            return base + ('' if url.startswith('/') else '/') + url

        favicon_url = _abs(cfg.get('favicon', ''))
        logo_url = _abs(cfg.get('logo', ''))
        og_image_url = _abs(cfg.get('og_image', ''))
        canonical = cfg.get('canonical_url', '')

        lines.append(f'<meta name="description" content="{cfg.get("description", "")}">')
        lines.append(f'<meta name="keywords" content="{cfg.get("keywords", "")}">')
        lines.append(f'<meta name="author" content="{cfg.get("author", "")}">')
        lines.append(f'<meta name="robots" content="{cfg.get("robots", "index,follow")}">')
        if canonical:
            lines.append(f'<link rel="canonical" href="{canonical}">')
        if favicon_url:
            lines.append(f'<link rel="icon" type="image/png" href="{favicon_url}">')
            lines.append(f'<link rel="apple-touch-icon" href="{favicon_url}">')
        if cfg.get('theme_color'):
            lines.append(f'<meta name="theme-color" content="{cfg["theme_color"]}">')
        lines.append(f'<meta name="language" content="{cfg.get("language", "zh-CN")}">')
        lines.append(f'<meta name="copyright" content="{cfg.get("copyright", "")}">')

        # Open Graph
        lines.append('<meta property="og:type" content="website">')
        lines.append(f'<meta property="og:title" content="{full_title}">')
        lines.append(f'<meta property="og:description" content="{cfg.get("description", "")}">')
        if canonical:
            lines.append(f'<meta property="og:url" content="{canonical}">')
        if og_image_url:
            lines.append(f'<meta property="og:image" content="{og_image_url}">')
        lines.append(f'<meta property="og:site_name" content="{cfg.get("site_name", "")}">')
        lines.append(f'<meta property="og:locale" content="zh_CN">')

        # Twitter Card
        lines.append('<meta name="twitter:card" content="summary_large_image">')
        lines.append(f'<meta name="twitter:title" content="{full_title}">')
        lines.append(f'<meta name="twitter:description" content="{cfg.get("description", "")}">')
        if og_image_url:
            lines.append(f'<meta name="twitter:image" content="{og_image_url}">')

        # JSON-LD
        json_ld = {
            "@context": "https://schema.org", "@type": "WebApplication",
            "name": title, "description": cfg.get('description', ''),
            "url": canonical,
            "author": {"@type": "Person", "name": cfg.get('author', 'Leon')},
            "inLanguage": cfg.get('language', 'zh-CN'), "operatingSystem": "Web"
        }
        if logo_url:
            json_ld["logo"] = logo_url
        if og_image_url:
            json_ld["image"] = og_image_url
        lines.append(f'<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>')

        if cfg.get('extra_head'):
            lines.append(cfg['extra_head'])

        return '\n    '.join(lines)

    # 注册为 Jinja2 全局函数
    app.jinja_env.globals['seo_meta'] = seo_meta
    app.jinja_env.globals['seo_meta_dynamic'] = seo_meta_dynamic
    app.jinja_env.globals['seo_config'] = get_seo_config

    def seo_canonical_url():
        """生成当前页面的公网 canonical URL（用 site_config 中的公网域名 + request.path）"""
        cfg = get_seo_config()
        canon = cfg.get('canonical_url', '')
        if canon:
            parsed = urlparse(canon)
            base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else f"http://119.145.17.34:{port}"
        else:
            base = f"http://119.145.17.34:{port}"
        return base + request.path

    app.jinja_env.globals['seo_canonical_url'] = seo_canonical_url

    # context_processor 注入 seo 变量
    @app.context_processor
    def inject_seo():
        return {'seo': get_seo_config(), 'seo_project_id': project_id}

    # ==================== API 路由 ====================

    @app.route('/api/site-config', methods=['GET'])
    @_require_token
    def get_site_config():
        """获取站点配置"""
        return jsonify(get_seo_config())

    @app.route('/api/site-config', methods=['PUT', 'POST'])
    @_require_token
    def update_site_config():
        """更新站点配置"""
        try:
            data = request.get_json(force=True)
            cfg = get_seo_config()
            cfg.update(data)
            _save_config(app.config['SEO_CONFIG_PATH'], cfg)
            return jsonify({"success": True, "config": cfg})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # ==================== SEO 路由 ====================

    @app.route('/robots.txt')
    def robots():
        """robots.txt 供搜索引擎爬取"""
        cfg = get_seo_config()
        robots_content = cfg.get('robots', 'index,follow')
        allow = "Allow: /" if "index" in robots_content else "Disallow: /"
        txt = f"User-agent: *\n{allow}\n\nSitemap: {cfg.get('canonical_url', '').rstrip('/')}/sitemap.xml\n"
        return Response(txt, mimetype='text/plain')

    @app.route('/sitemap.xml')
    def sitemap():
        """sitemap.xml 提升搜索引擎收录"""
        cfg = get_seo_config()
        url = cfg.get('canonical_url', '').rstrip('/')
        if not url:
            url = f"{base_url}:{port}"
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
