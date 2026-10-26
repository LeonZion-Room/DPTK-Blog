#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信名片H5签名服务
使用Python Flask实现，包含后台管理功能
"""

import time
import hashlib
import json
import requests
import os
import uuid
import datetime
import argparse
import socket
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_from_directory, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from seo_helper import init_seo
from card_seo import init_card_seo

app = Flask(__name__, static_folder='../', static_url_path='/')
app.secret_key = 'wechat_card_secret_key'
app.config['APPLICATION_ROOT'] = ''
# 修正：APPLICATION_ROOT 为空会导致 session cookie Path= 为空，登录态丢失
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
CORS(app)  # 允许跨域请求

# SEO / 对外展示信息注入
# 微信名片 SEO 由名片自身数据（card_config.json）驱动，不由 Leon-Control 远程控制
# （init_card_seo 在 load_config 定义后调用，见文件下方）

# 添加enumerate过滤器
@app.template_filter('enumerate')
def jinja2_enumerate(iterable):
    return enumerate(iterable)

# 添加now函数到模板上下文
@app.context_processor
def inject_now():
    return {'now': lambda: int(time.time())}

# 微信配置
APP_ID = 'wx3af2c6733acfc3e2'  # 测试环境AppID
APP_SECRET = '6919e48b7044b36eda39ac4ce797f8a3'  # 测试环境AppSecret

# 缓存
access_token = None
token_expire = 0
jsapi_ticket = None
ticket_expire = 0

# 上传配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 名片配置文件
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'card_config.json')

# 确保上传目录存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    print(f"创建上传目录: {UPLOAD_FOLDER}")
else:
    print(f"上传目录已存在: {UPLOAD_FOLDER}")

# 默认配置
default_config = {
    'basicInfo': {
        'name': '谢达',
        'title': '深圳市龙岗区坂田街道办事处',
        'title2': '党工委副书记、办事处主任',
        'phone': '18922878666',
        'email': 'szxieda@163.com',
        'logo': 'https://img.cdn1.vip/i/69a0748ac1626_1772123274.png',
        'company': '深圳市龙岗区坂田街道办事处',
        'address': ''
    },
    'groups': [
        {
            'id': 'default',
            'name': '默认分组',
            'description': '默认页面分组'
        }
    ],
    'pages': [
        {
            'id': 'home',
            'title': '首页',
            'groupId': 'default',
            'sections': [
                {'type': 'title', 'level': 1, 'title': '个人简介'},
                {
                    'type': 'grid',
                    'images': [
                        {'src': 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', 'jump': 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg'},
                        {'src': 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', 'jump': 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg'},
                        {'src': 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', 'jump': 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg'},
                        {'src': 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', 'jump': 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg'}
                    ]
                },
                {'type': 'title', 'level': 2, 'title': '工作经历'},
                {'type': 'video', 'src': 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.mp4', 'poster': 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg'},
                {'type': 'title', 'level': 3, 'title': '教育背景'},
                {'type': 'image', 'src': 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', 'jump': 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp'}
            ]
        }
    ],
    'settings': {
        'showCallConfirm': True,
        'defaultPage': 'home'
    }
}

# 加载配置
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 迁移旧的 btnTop 像素值为 btnTopPercent 百分比（幂等）
            try:
                migrate_btn_top_percent(config)
            except Exception as e:
                print(f"迁移btnTop百分比时出错: {e}")
            # 为缺失 uid 的组件自动分配唯一ID（幂等，纯新增字段）
            try:
                ensure_section_uids(config)
            except Exception as e:
                print(f"分配组件UID时出错: {e}")
            return config
        except:
            return default_config
    return default_config

# 保存配置
def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ============ 按钮距顶部距离：百分比自适应 ============

def get_image_ratio(url):
    """从本地 uploads 图片解析宽高比(width/height)，失败返回 None"""
    if not url:
        return None
    filename = None
    if 'uploads/' in url:
        filename = url.split('uploads/')[-1].split('?')[0]
    elif '/' not in url and ':' not in url:
        filename = url
    if not filename:
        return None
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return None
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
        return (w / h) if h else None
    except Exception:
        return None

def migrate_btn_top_percent(config):
    """将旧的 btnTop 像素值迁移为 btnTopPercent 百分比（以手机 375px 宽度为参考）"""
    changed = False
    for page in config.get('pages', []):
        for section in page.get('sections', []):
            if section.get('type') == 'contact' and 'btnTopPercent' not in section and section.get('btnTop'):
                ratio = get_image_ratio(section.get('customBgImage'))
                if not ratio:
                    ratio = 1.8  # 默认宽高比兜底
                ref_card_width = 375
                img_height = ref_card_width / ratio
                try:
                    pct = round(float(section['btnTop']) / img_height * 100)
                except (ValueError, TypeError):
                    pct = 30
                section['btnTopPercent'] = max(0, min(100, pct))
                changed = True
    if changed:
        save_config(config)
    return config

# ================= 组件唯一ID (uid) 与映射组件机制（纯新增，不影响原有渲染/样式） =================

def iter_all_sections(config):
    """遍历配置中所有页面下的所有区块（含 tabs 内嵌区块），产出 (page, section)"""
    for page in config.get('pages', []):
        for section in page.get('sections', []):
            yield page, section
            if section.get('type') == 'tabs':
                for tab in section.get('tabs', []):
                    for t_sec in tab.get('sections', []):
                        yield page, t_sec

def ensure_section_uids(config):
    """为所有缺失 uid 的组件分配唯一ID（幂等，只新增字段不改原有字段）"""
    changed = False
    used = set()
    for page, section in iter_all_sections(config):
        uid = section.get('uid')
        if uid:
            used.add(uid)
    for page, section in iter_all_sections(config):
        if not section.get('uid'):
            uid = 'sec_' + uuid.uuid4().hex[:12]
            while uid in used:
                uid = 'sec_' + uuid.uuid4().hex[:12]
            section['uid'] = uid
            used.add(uid)
            changed = True
    if changed:
        save_config(config)
    return config

def find_section_by_uid(config, uid):
    """按 uid 查找组件，返回 (page, section) 或 (None, None)"""
    for page, section in iter_all_sections(config):
        if section.get('uid') == uid:
            return page, section
    return None, None

def get_mapping_ref_uids(section):
    """获取映射组件的引用ID列表（支持 refUids 数组与单个 refUid 兼容）"""
    if section.get('refUids') and isinstance(section.get('refUids'), list):
        uids = []
        for u in section['refUids']:
            if not u:
                continue
            # 兼容：单个元素可能是空格/逗号分隔的多个UID
            for piece in str(u).replace(',', ' ').split():
                piece = piece.strip()
                if piece:
                    uids.append(piece)
        return uids
    ref_uid = section.get('refUid', '')
    if ref_uid and str(ref_uid).strip():
        return [ref_uid]
    return []

def resolve_mapping_section(config, section, seen=None):
    """将单个映射引用解析为其引用的组件内容（深拷贝），支持链式映射，防循环"""
    if section.get('type') != 'mapping':
        return section
    ref_uid = section.get('refUid', '')
    seen = seen or set()
    if not ref_uid:
        return {'type': 'code', 'content': '映射组件未配置引用ID'}
    if ref_uid in seen:
        return {'type': 'code', 'content': '映射组件存在循环引用: ' + ref_uid}
    page, target = find_section_by_uid(config, ref_uid)
    if not target:
        return {'type': 'code', 'content': '映射组件引用的组件不存在: ' + ref_uid}
    import copy as _copy
    resolved = _copy.deepcopy(target)
    if resolved.get('type') == 'mapping':
        resolved = resolve_mapping_section(config, resolved, seen | {ref_uid})
    resolved['_mappingOf'] = ref_uid
    # 保留映射组件自身的外层配置（若显式设置）
    for key in ('margin', 'borderRadius'):
        if key in section and section.get(key) not in (None, 0, '', {}):
            resolved[key] = section.get(key)
    return resolved

def resolve_section_flat(config, section):
    """将一个 section 解析为可能展开的 section 列表（mapping 支持多个有序引用）"""
    if section.get('type') != 'mapping':
        return [resolve_mapping_section(config, section)]
    ref_uids = get_mapping_ref_uids(section)
    if not ref_uids:
        return [{'type': 'code', 'content': '映射组件未配置引用ID'}]
    resolved_list = []
    for ref_uid in ref_uids:
        resolved = resolve_mapping_section(config, {'type': 'mapping', 'refUid': ref_uid})
        if resolved.get('type') == 'mapping' and resolved.get('refUids'):
            resolved_list.extend(resolve_section_flat(config, resolved))
        else:
            resolved_list.append(resolved)
    return resolved_list

def resolve_all_mappings(config):
    """返回一份解析后的配置副本（不修改源配置），供渲染接口使用；非 mapping 组件原样保留"""
    import copy as _copy
    resolved_config = _copy.deepcopy(config)
    for page in resolved_config.get('pages', []):
        new_sections = []
        for section in page.get('sections', []):
            new_sections.extend(resolve_section_flat(resolved_config, section))
        page['sections'] = new_sections
        for section in page.get('sections', []):
            if section.get('type') == 'tabs':
                for tab in section.get('tabs', []):
                    new_tab_sections = []
                    for s in tab.get('sections', []):
                        new_tab_sections.extend(resolve_section_flat(resolved_config, s))
                    tab['sections'] = new_tab_sections
    return resolved_config

# 检查文件类型
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 微信名片自有 SEO（在 load_config 定义后初始化）
init_card_seo(app, config_loader=load_config, port=8000)

def get_access_token():
    """获取access_token"""
    global access_token, token_expire
    
    if access_token and time.time() < token_expire:
        return access_token
    
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APP_ID}&secret={APP_SECRET}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if 'access_token' in data:
            access_token = data['access_token']
            token_expire = time.time() + (data['expires_in'] - 300)  # 提前5分钟刷新
            return access_token
        else:
            return None
    except Exception as e:
        print(f"获取access_token失败: {e}")
        return None

def get_jsapi_ticket():
    """获取jsapi_ticket"""
    global jsapi_ticket, ticket_expire
    
    if jsapi_ticket and time.time() < ticket_expire:
        return jsapi_ticket
    
    token = get_access_token()
    if not token:
        return None
    
    url = f"https://api.weixin.qq.com/cgi-bin/ticket/getticket?access_token={token}&type=jsapi"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if 'ticket' in data:
            jsapi_ticket = data['ticket']
            ticket_expire = time.time() + (data['expires_in'] - 300)  # 提前5分钟刷新
            return jsapi_ticket
        else:
            return None
    except Exception as e:
        print(f"获取jsapi_ticket失败: {e}")
        return None

def generate_signature(url):
    """生成微信签名"""
    ticket = get_jsapi_ticket()
    if not ticket:
        return None
    
    nonce_str = str(int(time.time() * 1000))
    timestamp = str(int(time.time()))
    
    # 按照微信要求的顺序拼接
    string1 = f"jsapi_ticket={ticket}&noncestr={nonce_str}&timestamp={timestamp}&url={url}"
    
    # SHA1加密
    signature = hashlib.sha1(string1.encode('utf-8')).hexdigest()
    
    return {
        'appId': APP_ID,
        'timestamp': timestamp,
        'nonceStr': nonce_str,
        'signature': signature
    }

# 登录装饰器
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # API 请求返回 JSON 401，页面请求重定向到登录
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': '未登录', 'redirect': url_for('login')}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# 登录页面
@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 简单的登录验证（实际项目中应该使用更安全的方式）
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('用户名或密码错误')
    return render_template('login.html')

# 登出
@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# 后台管理首页
@app.route('/admin')
@login_required
def admin():
    config = load_config()
    return render_template('admin.html', config=config)

# 页面属性视图
@app.route('/admin/attributes')
@login_required
def attributes_view():
    config = load_config()
    if 'pages' not in config:
        config['pages'] = []
    return render_template('attributes_view.html', config=config)

@app.route('/admin/mindmap')
@login_required
def mind_map_view():
    config = load_config()
    if 'pages' not in config:
        config['pages'] = []
    return render_template('mind_map.html', config=config)

# 一键导出静态站（预渲染全部名片页到 dist-static/，供 GitHub -> Cloudflare Pages）
@app.route('/admin/export-static', methods=['GET'])
@login_required
def export_static_page():
    import static_export as se
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    info = se.last_export_info(project_root)
    config = load_config()
    return render_template('export_static.html', config=config, info=info,
                           total_pages=len(config.get('pages', [])),
                           out_rel='dist-static',
                           current_domain=current_domain)

@app.route('/admin/export-static/run', methods=['POST'])
@login_required
def export_static_run():
    import static_export as se
    import urllib.parse
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_config()

    def render_html_fn(pid):
        with app.test_request_context('/?page=' + urllib.parse.quote(pid)):
            return index_dynamic()

    try:
        stats = se.export_all(render_html_fn, config, resolve_all_mappings,
                              current_domain, project_root,
                              media_local=True, media_source='http://127.0.0.1:8000')
        if stats['errors']:
            flash('静态导出完成（%d 页），但有 %d 条告警：%s'
                  % (stats['pages'], len(stats['errors']),
                     '；'.join(stats['errors'][:5])))
        else:
            flash('静态导出成功：%d 个页面 -> %s/（约 %.1f MB），可推 GitHub 上线'
                  % (stats['pages'], stats['out_rel'],
                     stats['bytes'] / 1024 / 1024))
    except Exception as e:
        flash('静态导出失败：%s' % e)
    return redirect(url_for('export_static_page'))


# 批量设置页面展示信息（纯新增模块，替代原「名片信息设置」）
@app.route('/admin/batch-display', methods=['GET'])
@login_required
def batch_display():
    config = load_config()
    pages = config.get('pages', [])
    # 预取每个页面的 contact 名片信息区块，供界面回显
    for page in pages:
        contact_section = None
        for sec in page.get('sections', []):
            if sec.get('type') == 'contact':
                contact_section = sec
                break
        page['contact_section'] = contact_section
    return render_template('batch_display.html', pages=pages)


@app.route('/admin/api-docs', methods=['GET'])
@login_required
def api_docs():
    """AI 管理 API 文档页面"""
    return render_template('api_docs.html')


@app.route('/admin/batch-share', methods=['GET'])
@login_required
def batch_share():
    """批量修改页面分享设置（分享标题/描述/图标）"""
    config = load_config()
    pages = config.get('pages', [])
    return render_template('batch_share.html', pages=pages, current_domain=current_domain)


@app.route('/api/pages/batch-share', methods=['POST'])
def api_pages_batch_share():
    """批量保存页面分享设置"""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or 'pages' not in data:
        return jsonify({'success': False, 'error': '缺少 pages 数组'}), 400

    items = data.get('pages')
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'error': 'pages 不能为空'}), 400

    config = load_config()
    results = []
    for item in items:
        if not isinstance(item, dict) or not item.get('pageId'):
            results.append({'pageId': item.get('pageId') if isinstance(item, dict) else None, 'success': False, 'error': '缺少 pageId'})
            continue

        page_id = str(item['pageId'])
        page = None
        for p in config.get('pages', []):
            if str(p.get('id')) == page_id:
                page = p
                break

        if not page:
            results.append({'pageId': page_id, 'success': False, 'error': '页面不存在'})
            continue

        changed = False
        for key in ('share_title', 'share_desc', 'share_icon'):
            if key in item:
                page[key] = item[key]
                changed = True

        results.append({'pageId': page_id, 'success': True, 'changed': changed})

    if any(r.get('changed') for r in results):
        save_config(config)
    return jsonify({'success': True, 'results': results})


# 页面管理
@app.route('/admin/pages')
@login_required
def pages():
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
    # 确保groups键存在
    if 'groups' not in config or not config['groups']:
        config['groups'] = [{
            'id': 'default',
            'name': '默认分组',
            'description': '默认页面分组'
        }]
        save_config(config)
    # 为页面设置默认分组
    for page in config['pages']:
        if 'groupId' not in page:
            page['groupId'] = 'default'
    save_config(config)
    # 对页面进行排序：先按分组ID，再按标题字母顺序
    sorted_pages = sorted(config['pages'], key=lambda p: (p.get('groupId', 'default'), p.get('title', '')))
    return render_template('pages.html', pages=sorted_pages, groups=config['groups'], current_domain=current_domain)

# 创建页面
@app.route('/admin/pages/create', methods=['GET', 'POST'])
@login_required
def create_page():
    if request.method == 'POST':
        config = load_config()
        # 支持两种参数名：form表单提交和API提交
        page_id = request.form.get('page_id', '').lower().replace(' ', '_')
        if not page_id:
            page_id = request.form.get('id', '').lower().replace(' ', '_')
        page_title = request.form.get('page_title', '')
        if not page_title:
            page_title = request.form.get('title', '')
        
        if not page_id or not page_title:
            flash('页面ID和标题不能为空')
            return redirect(url_for('create_page'))
        
        # 检查页面ID是否已存在
        for page in config.get('pages', []):
            if page['id'] == page_id:
                flash('页面ID已存在')
                return redirect(url_for('create_page'))
        
        # 创建新页面
        new_page = {
            'id': page_id,
            'title': page_title,
            'groupId': request.form.get('group_id', 'default'),
            'sections': [],
            'share_title': request.form.get('share_title', ''),
            'share_desc': request.form.get('share_desc', ''),
            'share_icon': request.form.get('share_icon', '')
        }
        
        mobile_gap = request.form.get('mobile_gap')
        if mobile_gap is not None and mobile_gap != '':
            new_page['mobile_gap'] = int(mobile_gap)
        else:
            new_page['mobile_gap'] = 10
        
        # 保存名片个人信息模块背景设置
        card_bg_theme = request.form.get('card_bg_theme')
        if card_bg_theme:
            new_page['card_bg_theme'] = card_bg_theme
        
        card_custom_bg_image = request.form.get('card_custom_bg_image', '').strip()
        if card_custom_bg_image:
            new_page['card_custom_bg_image'] = card_custom_bg_image
        
        # 确保pages键存在
        if 'pages' not in config:
            config['pages'] = []
        
        config['pages'].append(new_page)
        save_config(config)
        flash('页面创建成功')
        return redirect(url_for('pages'))
    
    # 确保groups键存在
    config = load_config()
    if 'groups' not in config or not config['groups']:
        config['groups'] = [{
            'id': 'default',
            'name': '默认分组',
            'description': '默认页面分组'
        }]
        save_config(config)
    return render_template('create_page.html', groups=config['groups'])

# 编辑页面
@app.route('/admin/pages/edit/<page_id>', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    # 确保groups键存在
    if 'groups' not in config or not config['groups']:
        config['groups'] = [{
            'id': 'default',
            'name': '默认分组',
            'description': '默认页面分组'
        }]
    
    page = None
    
    for p in config['pages']:
        if p['id'] == page_id:
            page = p
            break
    
    if not page:
        flash('页面不存在')
        return redirect(url_for('pages'))
    
    if request.method == 'POST':
        new_page_id = request.form.get('page_id', page['id'])
        new_title = request.form.get('page_title', page['title'])
        
        # 检查新的页面ID是否与其他页面冲突
        if new_page_id != page_id:
            for p in config['pages']:
                if p['id'] == new_page_id:
                    flash('页面ID已存在')
                    return redirect(url_for('edit_page', page_id=page_id))
            
            # 更新默认页面设置（如果需要）
            if config.get('settings', {}).get('defaultPage') == page_id:
                config['settings']['defaultPage'] = new_page_id
            
            # 更新所有引用该页面ID的地方（比如轮播图跳转链接）
            old_url_param = f'page={page_id}'
            new_url_param = f'page={new_page_id}'
            for p in config['pages']:
                # 跳过正在修改的页面，防止修改自身内容
                if p['id'] == page_id:
                    continue
                for section in p.get('sections', []):
                    if section.get('type') == 'carousel':
                        for item in section.get('items', []):
                            if item.get('jump'):
                                item['jump'] = item['jump'].replace(old_url_param, new_url_param)
                    # 检查其他类型的跳转链接
                    if 'jump' in section:
                        section['jump'] = section['jump'].replace(old_url_param, new_url_param)
                    # 检查tabs中的跳转
                    if section.get('type') == 'tabs':
                        for tab in section.get('tabs', []):
                            for tab_section in tab.get('sections', []):
                                if 'jump' in tab_section:
                                    tab_section['jump'] = tab_section['jump'].replace(old_url_param, new_url_param)
                    # 检查grid中的跳转
                    if section.get('type') == 'grid':
                        for img in section.get('images', []):
                            if 'jump' in img:
                                img['jump'] = img['jump'].replace(old_url_param, new_url_param)
                    # 检查iconRow中的跳转
                    if section.get('type') == 'iconRow':
                        for icon in section.get('icons', []):
                            if 'jump' in icon:
                                icon['jump'] = icon['jump'].replace(old_url_param, new_url_param)
            
            # 更新页面ID
            page['id'] = new_page_id
        
        # 更新其他字段
        page['title'] = new_title
        page['groupId'] = request.form.get('group_id', page.get('groupId', 'default'))
        page['share_title'] = request.form.get('share_title', page.get('share_title', ''))
        page['share_desc'] = request.form.get('share_desc', page.get('share_desc', ''))
        page['share_icon'] = request.form.get('share_icon', page.get('share_icon', ''))
        
        mobile_gap = request.form.get('mobile_gap')
        if mobile_gap is not None and mobile_gap != '':
            page['mobile_gap'] = int(mobile_gap)
        
        # 保存名片个人信息模块背景设置
        card_bg_theme = request.form.get('card_bg_theme')
        if card_bg_theme:
            page['card_bg_theme'] = card_bg_theme
        elif 'card_bg_theme' in page and card_bg_theme == '':
            del page['card_bg_theme']
        
        card_custom_bg_image = request.form.get('card_custom_bg_image', '').strip()
        if card_custom_bg_image:
            page['card_custom_bg_image'] = card_custom_bg_image
        elif 'card_custom_bg_image' in page and not card_custom_bg_image:
            del page['card_custom_bg_image']

        # 保存页面背景设置
        page_bg_theme = request.form.get('page_bg_theme', '').strip()
        if page_bg_theme:
            page['page_bg_theme'] = page_bg_theme
        elif 'page_bg_theme' in page:
            del page['page_bg_theme']

        page_custom_bg_image = request.form.get('page_custom_bg_image', '').strip()
        if page_custom_bg_image:
            page['page_custom_bg_image'] = page_custom_bg_image
        elif 'page_custom_bg_image' in page and not page_custom_bg_image:
            del page['page_custom_bg_image']

        page_bg_scale_mode = request.form.get('page_bg_scale_mode', '').strip()
        if page_bg_scale_mode:
            page['page_bg_scale_mode'] = page_bg_scale_mode
        elif 'page_bg_scale_mode' in page:
            del page['page_bg_scale_mode']

        save_config(config)
        flash('页面信息更新成功')
        return redirect(url_for('pages'))
    
    return render_template('edit_page.html', page=page, groups=config['groups'])

# 删除页面
@app.route('/admin/pages/delete/<page_id>', methods=['POST'])
@login_required
def delete_page(page_id):
    try:
        config = load_config()
        if 'pages' not in config:
            return jsonify({'success': False, 'error': '页配置不存在'})
        
        pages = config['pages']
        new_pages = [page for page in pages if page['id'] != page_id]
        
        if len(new_pages) != len(pages):
            config['pages'] = new_pages
            if config.get('settings', {}).get('defaultPage') == page_id and new_pages:
                config['settings']['defaultPage'] = new_pages[0]['id']
            save_config(config)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '页面不存在'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/pages/update-title/<page_id>', methods=['POST'])
@login_required
def update_page_title(page_id):
    try:
        config = load_config()
        if 'pages' not in config:
            return jsonify({'success': False, 'error': '页面配置不存在'})
        
        new_title = (request.form.get('title') or (request.get_json(silent=True) or {}).get('title') or '').strip()
        if not new_title:
            return jsonify({'success': False, 'error': '标题不能为空'})
        
        for page in config['pages']:
            if page['id'] == page_id:
                page['title'] = new_title
                save_config(config)
                return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': '页面不存在'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/pages/add', methods=['POST'])
@login_required
def add_page():
    try:
        config = load_config()
        if 'pages' not in config:
            config['pages'] = []
        
        page_id = request.form.get('id', '').strip()
        page_title = request.form.get('title', '').strip()
        
        if not page_id or not page_title:
            return jsonify({'success': False, 'error': '页面ID和标题不能为空'})
        
        for page in config['pages']:
            if page['id'] == page_id:
                return jsonify({'success': False, 'error': '页面ID已存在'})
        
        new_page = {
            'id': page_id,
            'title': page_title,
            'groupId': request.form.get('groupId', 'default'),
            'sections': [
                {'type': 'title', 'level': 1, 'title': '页面标题'}
            ]
        }
        
        config['pages'].append(new_page)
        save_config(config)
        return jsonify({'success': True, 'page': new_page})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 更新页面备注
@app.route('/admin/pages/update-note', methods=['POST'])
@login_required
def update_page_note():
    try:
        config = load_config()
        page_id = request.form.get('pageId', '').strip()
        note = request.form.get('note', '').strip()
        
        if not page_id:
            return jsonify({'success': False, 'error': '页面ID不能为空'})
        
        for page in config['pages']:
            if page['id'] == page_id:
                if note:
                    page['note'] = note
                elif 'note' in page:
                    del page['note']
                save_config(config)
                return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': '页面不存在'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 保存节点备注（中间节点，不对应具体页面）
@app.route('/admin/node-notes/save', methods=['POST'])
@login_required
def save_node_note():
    try:
        config = load_config()
        path = request.form.get('path', '').strip()
        note = request.form.get('note', '').strip()
        
        if not path:
            return jsonify({'success': False, 'error': '路径不能为空'})
        
        if 'nodeNotes' not in config:
            config['nodeNotes'] = {}
        
        if note:
            config['nodeNotes'][path] = note
        elif path in config['nodeNotes']:
            del config['nodeNotes'][path]
        
        save_config(config)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 设置默认页面
@app.route('/admin/pages/set-default/<page_id>', methods=['POST'])
@login_required
def set_default_page(page_id):
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    # 检查页面是否存在
    page_exists = False
    for page in config['pages']:
        if page['id'] == page_id:
            page_exists = True
            break
    
    if page_exists:
        # 确保settings键存在
        if 'settings' not in config:
            config['settings'] = {}
        config['settings']['defaultPage'] = page_id
        save_config(config)
        flash('默认页面设置成功')
    else:
        flash('页面不存在')
    
    return redirect(url_for('pages'))

# 复制页面
@app.route('/admin/pages/copy/<page_id>', methods=['POST'])
@login_required
def copy_page(page_id):
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    # 查找要复制的页面
    source_page = None
    for page in config['pages']:
        if page['id'] == page_id:
            source_page = page
            break
    
    if not source_page:
        flash('页面不存在')
        return redirect(url_for('pages'))
    
    # 生成新的页面ID (在原ID基础上添加 _copy 后缀)
    new_page_id = f"{page_id}_copy"
    # 如果已经存在，添加数字后缀
    counter = 1
    existing_ids = [p['id'] for p in config['pages']]
    while new_page_id in existing_ids:
        new_page_id = f"{page_id}_copy{counter}"
        counter += 1
    
    # 手动完整复制页面数据，避免deepcopy的问题
    new_page = {}
    # 复制基本字段
    for key in source_page:
        if key == 'sections':
            # 处理sections数组
            new_sections = []
            for section in source_page['sections']:
                new_section = {}
                for sec_key in section:
                    if sec_key == 'tabs':
                        # 处理tabs数组
                        new_tabs = []
                        for tab in section['tabs']:
                            new_tab = {}
                            for tab_key in tab:
                                if tab_key == 'sections':
                                    # 处理tab内的sections
                                    new_tab_sections = []
                                    for tab_sec in tab['sections']:
                                        new_tab_sec = {}
                                        for ts_key in tab_sec:
                                            new_tab_sec[ts_key] = tab_sec[ts_key]
                                        new_tab_sections.append(new_tab_sec)
                                    new_tab['sections'] = new_tab_sections
                                else:
                                    new_tab[tab_key] = tab[tab_key]
                            new_tabs.append(new_tab)
                        new_section['tabs'] = new_tabs
                    elif sec_key == 'items':
                        # 处理carousel的items数组
                        new_items = []
                        for item in section['items']:
                            new_item = {}
                            for i_key in item:
                                new_item[i_key] = item[i_key]
                            new_items.append(new_item)
                        new_section['items'] = new_items
                    elif sec_key == 'images':
                        # 处理grid的images数组
                        new_images = []
                        for img in section['images']:
                            new_img = {}
                            for img_key in img:
                                new_img[img_key] = img[img_key]
                            new_images.append(new_img)
                        new_section['images'] = new_images
                    elif sec_key == 'icons':
                        # 处理iconRow的icons数组
                        new_icons = []
                        for icon in section['icons']:
                            new_icon = {}
                            for icon_key in icon:
                                new_icon[icon_key] = icon[icon_key]
                            new_icons.append(new_icon)
                        new_section['icons'] = new_icons
                    else:
                        new_section[sec_key] = section[sec_key]
                new_sections.append(new_section)
            new_page['sections'] = new_sections
        else:
            new_page[key] = source_page[key]
    
    # 设置新ID和标题
    new_page['id'] = new_page_id
    new_page['title'] = f"{source_page.get('title', '副本')} - 副本"
    
    # 添加到配置中
    config['pages'].append(new_page)
    save_config(config)
    
    flash(f'页面副本创建成功！新页面ID: {new_page_id}')
    return redirect(url_for('pages'))

# 分组管理
@app.route('/admin/groups')
@login_required
def groups():
    config = load_config()
    # 确保groups键存在
    if 'groups' not in config or not config['groups']:
        config['groups'] = [{
            'id': 'default',
            'name': '默认分组',
            'description': '默认页面分组'
        }]
        save_config(config)
    return render_template('groups.html', groups=config['groups'], pages=config.get('pages', []), current_domain=current_domain)

# 创建分组
@app.route('/admin/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        config = load_config()
        # 确保groups键存在
        if 'groups' not in config:
            config['groups'] = []
        
        group_id = request.form.get('group_id', '').lower().replace(' ', '_')
        group_name = request.form.get('group_name', '')
        
        if not group_id or not group_name:
            flash('分组ID和名称不能为空')
            return redirect(url_for('create_group'))
        
        # 检查分组ID是否已存在
        for group in config.get('groups', []):
            if group['id'] == group_id:
                flash('分组ID已存在')
                return redirect(url_for('create_group'))
        
        # 创建新分组
        new_group = {
            'id': group_id,
            'name': group_name,
            'description': request.form.get('group_description', '')
        }
        
        config['groups'].append(new_group)
        save_config(config)
        flash('分组创建成功')
        return redirect(url_for('groups'))
    return render_template('create_group.html')

# 编辑分组
@app.route('/admin/groups/edit/<group_id>', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    config = load_config()
    # 确保groups键存在
    if 'groups' not in config:
        config['groups'] = []
        save_config(config)
    
    group = None
    for g in config['groups']:
        if g['id'] == group_id:
            group = g
            break
    
    if not group:
        flash('分组不存在')
        return redirect(url_for('groups'))
    
    if request.method == 'POST':
        new_group_id = request.form.get('group_id', group['id'])
        new_name = request.form.get('group_name', group['name'])
        
        # 检查新的分组ID是否与其他分组冲突
        if new_group_id != group_id:
            for g in config['groups']:
                if g['id'] == new_group_id:
                    flash('分组ID已存在')
                    return redirect(url_for('edit_group', group_id=group_id))
            
            # 更新所有页面的groupId
            for page in config.get('pages', []):
                if page.get('groupId') == group_id:
                    page['groupId'] = new_group_id
            
            group['id'] = new_group_id
        
        group['name'] = new_name
        group['description'] = request.form.get('group_description', '')
        
        save_config(config)
        flash('分组信息更新成功')
        return redirect(url_for('groups'))
    
    return render_template('edit_group.html', group=group)

# 删除分组
@app.route('/admin/groups/delete/<group_id>', methods=['POST'])
@login_required
def delete_group(group_id):
    config = load_config()
    # 确保groups键存在
    if 'groups' not in config:
        config['groups'] = []
        save_config(config)
    
    # 不能删除默认分组
    if group_id == 'default':
        flash('不能删除默认分组')
        return redirect(url_for('groups'))
    
    # 检查该分组下是否有页面
    has_pages = False
    for page in config.get('pages', []):
        if page.get('groupId') == group_id:
            has_pages = True
            break
    
    if has_pages:
        flash('该分组下还有页面，无法删除，请先移动页面到其他分组')
        return redirect(url_for('groups'))
    
    groups = config['groups']
    new_groups = [group for group in groups if group['id'] != group_id]
    
    if len(new_groups) != len(groups):
        config['groups'] = new_groups
        save_config(config)
        flash('分组删除成功')
    else:
        flash('分组不存在')
    
    return redirect(url_for('groups'))

# 移动页面到分组
@app.route('/admin/pages/move/<page_id>/<group_id>', methods=['POST'])
@login_required
def move_page_to_group(page_id, group_id):
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
    # 确保groups键存在
    if 'groups' not in config or not config['groups']:
        config['groups'] = [{
            'id': 'default',
            'name': '默认分组',
            'description': '默认页面分组'
        }]
    
    # 查找页面
    page = None
    for p in config['pages']:
        if p['id'] == page_id:
            page = p
            break
    
    if not page:
        flash('页面不存在')
        return redirect(url_for('pages'))
    
    # 检查目标分组是否存在
    group_exists = False
    for g in config['groups']:
        if g['id'] == group_id:
            group_exists = True
            break
    
    if not group_exists:
        flash('目标分组不存在')
        return redirect(url_for('pages'))
    
    page['groupId'] = group_id
    save_config(config)
    flash('页面移动成功')
    return redirect(url_for('pages'))

# ================= 分组管理拖拽 API（纯新增，不影响原有路由） =================

def _build_group_tree(groups):
    """将扁平分组列表构建为树（支持 parent 嵌套）"""
    nodes = {g['id']: dict(g, children=[], pages=[]) for g in groups}
    roots = []
    for gid, node in nodes.items():
        parent = node.get('parent')
        if parent and parent in nodes and parent != gid:
            nodes[parent]['children'].append(node)
        else:
            roots.append(node)
    return roots

@app.route('/api/groups/tree', methods=['GET'])
@login_required
def api_groups_tree():
    """获取分组树（含每组的页面列表），供拖拽管理界面使用"""
    config = load_config()
    groups = config.get('groups', [])
    pages = config.get('pages', [])
    tree = _build_group_tree(groups)
    # 附加每组页面
    def attach_pages(node):
        node['pages'] = [p for p in pages if p.get('groupId') == node['id']]
        for child in node.get('children', []):
            attach_pages(child)
    for root in tree:
        attach_pages(root)
    return jsonify({'success': True, 'groups': tree, 'pages': pages})

@app.route('/api/groups/create', methods=['POST'])
@login_required
def api_group_create():
    """创建分组（支持 parent 嵌套）"""
    data = request.get_json(silent=True) or request.form
    config = load_config()
    if 'groups' not in config:
        config['groups'] = []

    # 分组ID自动生成：未提供时生成 g_ + 随机串；提供时校验唯一
    group_id = str(data.get('id') or data.get('group_id') or '').strip().lower().replace(' ', '_')
    group_name = str(data.get('name') or data.get('group_name') or '').strip()
    if not group_name:
        return jsonify({'success': False, 'error': '分组名称不能为空'}), 400

    existing_ids = set(g['id'] for g in config.get('groups', []))
    if group_id:
        if group_id in existing_ids:
            return jsonify({'success': False, 'error': '分组ID已存在'}), 400
    else:
        # 自动生成唯一ID
        import uuid as _uuid
        group_id = 'g_' + _uuid.uuid4().hex[:8]
        while group_id in existing_ids:
            group_id = 'g_' + _uuid.uuid4().hex[:8]

    parent = str(data.get('parent') or '').strip()
    if parent and parent not in existing_ids:
        return jsonify({'success': False, 'error': '父分组不存在'}), 400

    new_group = {
        'id': group_id,
        'name': group_name,
        'description': str(data.get('description') or data.get('group_description') or ''),
    }
    if parent:
        new_group['parent'] = parent
    config['groups'].append(new_group)
    save_config(config)
    return jsonify({'success': True, 'group': new_group})

@app.route('/api/groups/move', methods=['POST'])
@login_required
def api_group_move():
    """移动分组：设置 parent 实现嵌套，parent 为空则移到顶级"""
    data = request.get_json(silent=True) or request.form
    group_id = str(data.get('id') or data.get('groupId') or '').strip()
    parent = str(data.get('parent') or '').strip()
    if not group_id:
        return jsonify({'success': False, 'error': '缺少分组ID'}), 400

    config = load_config()
    groups = config.get('groups', [])
    group = None
    for g in groups:
        if g['id'] == group_id:
            group = g
            break
    if not group:
        return jsonify({'success': False, 'error': '分组不存在'}), 404

    if group_id == 'default':
        return jsonify({'success': False, 'error': '默认分组不能移动'}), 400

    if parent:
        if parent == group_id:
            return jsonify({'success': False, 'error': '不能把分组移动到自身'}), 400
        if parent not in [g['id'] for g in groups]:
            return jsonify({'success': False, 'error': '父分组不存在'}), 400
        # 防止循环嵌套：检查 parent 的祖先链中是否有 group_id
        cur = parent
        visited = set()
        while cur:
            if cur in visited:
                break
            visited.add(cur)
            if cur == group_id:
                return jsonify({'success': False, 'error': '不能移动到自己的子分组下'}), 400
            pg = next((g for g in groups if g['id'] == cur), None)
            cur = pg.get('parent') if pg else None
        group['parent'] = parent
    else:
        group.pop('parent', None)
    save_config(config)
    return jsonify({'success': True, 'group': group})

@app.route('/api/groups/delete', methods=['POST'])
@login_required
def api_group_delete():
    """删除分组（须为空；有子分组也禁止）"""
    data = request.get_json(silent=True) or request.form
    group_id = str(data.get('id') or data.get('groupId') or '').strip()
    if not group_id:
        return jsonify({'success': False, 'error': '缺少分组ID'}), 400
    if group_id == 'default':
        return jsonify({'success': False, 'error': '不能删除默认分组'}), 400

    config = load_config()
    groups = config.get('groups', [])
    # 检查子分组
    for g in groups:
        if g.get('parent') == group_id:
            return jsonify({'success': False, 'error': '该分组下还有子分组，无法删除'}), 400
    # 检查页面
    for page in config.get('pages', []):
        if page.get('groupId') == group_id:
            return jsonify({'success': False, 'error': '该分组下还有页面，无法删除'}), 400

    config['groups'] = [g for g in groups if g['id'] != group_id]
    save_config(config)
    return jsonify({'success': True})

@app.route('/api/groups/rename', methods=['POST'])
@login_required
def api_group_rename():
    """修改分组名称与描述"""
    data = request.get_json(silent=True) or request.form
    group_id = str(data.get('id') or data.get('groupId') or '').strip()
    new_name = str(data.get('name') or data.get('group_name') or '').strip()
    if not group_id:
        return jsonify({'success': False, 'error': '缺少分组ID'}), 400
    if not new_name:
        return jsonify({'success': False, 'error': '分组名称不能为空'}), 400

    config = load_config()
    groups = config.get('groups', [])
    group = None
    for g in groups:
        if g['id'] == group_id:
            group = g
            break
    if not group:
        return jsonify({'success': False, 'error': '分组不存在'}), 404

    group['name'] = new_name
    if 'description' in data:
        group['description'] = str(data.get('description') or '').strip()
    save_config(config)
    return jsonify({'success': True, 'group': group})

@app.route('/api/pages/move', methods=['POST'])
@login_required
def api_page_move():
    """移动页面到分组（拖拽）"""
    data = request.get_json(silent=True) or request.form
    page_id = str(data.get('pageId') or data.get('page_id') or '').strip()
    group_id = str(data.get('groupId') or data.get('group_id') or '').strip()
    if not page_id or not group_id:
        return jsonify({'success': False, 'error': '缺少页面ID或分组ID'}), 400

    config = load_config()
    page = None
    for p in config.get('pages', []):
        if p['id'] == page_id:
            page = p
            break
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404
    if group_id not in [g['id'] for g in config.get('groups', [])]:
        return jsonify({'success': False, 'error': '目标分组不存在'}), 404

    page['groupId'] = group_id
    save_config(config)
    return jsonify({'success': True, 'pageId': page_id, 'groupId': group_id})

# 编辑页面内容区块
@app.route('/admin/pages/sections/<page_id>', methods=['GET', 'POST'])
@login_required
def edit_page_sections(page_id):
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    page = None
    
    for p in config['pages']:
        if p['id'] == page_id:
            page = p
            break
    
    if not page:
        flash('页面不存在')
        return redirect(url_for('pages'))
    
    if request.method == 'POST':
        try:
            # 保存分享设置
            page['share_title'] = request.form.get('share_title', '')
            page['share_desc'] = request.form.get('share_desc', '')
            page['share_icon'] = request.form.get('share_icon', '')

            # 保存页面背景主题（渐变色）
            page_bg_theme = request.form.get('page_bg_theme', '').strip()
            if page_bg_theme:
                page['page_bg_theme'] = page_bg_theme
            elif 'page_bg_theme' in page:
                del page['page_bg_theme']

            # 保存页面背景自定义图片（URL 字段）
            # 统一处理：如果用户填了"uploads/xxx.png"或"http://...uploads/xxx.png"，都规整为裸文件名"xxx.png"
            page_custom_bg_image = request.form.get('page_custom_bg_image', '').strip()
            if page_custom_bg_image:
                # 去掉 URL 中可能的 uploads/ 前缀和域名，只保留文件名
                from urllib.parse import urlparse
                parsed = urlparse(page_custom_bg_image)
                if parsed.path:
                    raw = parsed.path
                else:
                    raw = page_custom_bg_image
                # 去掉前导 / 和 uploads/ 前缀
                raw = raw.lstrip('/')
                if raw.startswith('uploads/'):
                    raw = raw[len('uploads/'):]
                page['page_custom_bg_image'] = raw
            elif 'page_custom_bg_image' in page and not page_custom_bg_image:
                del page['page_custom_bg_image']

            # 保存页面背景缩放模式
            page_bg_scale_mode = request.form.get('page_bg_scale_mode', '').strip() or 'cover'
            page['page_bg_scale_mode'] = page_bg_scale_mode

            # 处理 multipart 上传（如果用户直接拖了文件而不是填 URL）
            uploaded_bg = request.files.get('page_custom_bg_image_file')
            if uploaded_bg and uploaded_bg.filename:
                from werkzeug.utils import secure_filename
                ext = os.path.splitext(uploaded_bg.filename)[1].lower()
                if ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                    fname = f"pagebg_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
                    save_path = os.path.join(UPLOAD_FOLDER, fname)
                    uploaded_bg.save(save_path)
                    # 只存文件名（不带 uploads/ 前缀）
                    page['page_custom_bg_image'] = fname
                    flash(f'页面背景图上传成功: {fname}')
                else:
                    flash(f'页面背景图格式不支持: {ext}')

            # 保存手机端容器间隙
            mobile_gap = request.form.get('mobile_gap')
            if mobile_gap is not None and mobile_gap != '':
                try:
                    page['mobile_gap'] = int(mobile_gap)
                except (ValueError, TypeError):
                    page['mobile_gap'] = 10
            
            # 处理区块编辑
            sections = []
            section_count = 0
            try:
                section_count = int(request.form.get('section_count', '0'))
            except (ValueError, TypeError):
                section_count = 0
            
            # 打印表单数据，用于调试
            print(f"表单数据: {dict(request.form)}")
            print(f"区块数量: {section_count}")
            
            for i in range(section_count):
                try:
                    # 直接从表单中获取所有可能的字段
                    section_type = request.form.get(f'section_type_{i}')
                    print(f"区块 {i} 类型: {section_type}")
                    
                    # 即使section_type不存在，也尝试根据其他字段推断类型
                    if not section_type:
                        # 检查是否有图片相关字段
                        if request.form.get(f'section_src_{i}'):
                            # 检查是否有poster字段来判断是视频还是图片
                            if request.form.get(f'section_poster_{i}'):
                                section_type = 'video'
                            else:
                                section_type = 'image'
                        # 检查是否有标题相关字段
                        elif request.form.get(f'section_title_{i}'):
                            section_type = 'title'
                        # 检查是否有图片网格相关字段
                        elif request.form.get(f'image_count_{i}'):
                            section_type = 'grid'
                        else:
                            print(f"跳过区块 {i}: 无类型信息")
                            continue
                    
                    if section_type == 'title':
                        section = {
                            'type': 'title',
                            'level': 1,
                            'title': request.form.get(f'section_title_{i}', ''),
                            'subtitle': request.form.get(f'section_subtitle_{i}', ''),
                            'color': request.form.get(f'section_color_{i}', ''),
                            'decorationColor': request.form.get(f'section_decorationColor_{i}', ''),
                            'logo': request.form.get(f'section_logo_{i}', ''),
                            'margin': 10,
                            'topSpacing': 40,
                            'bottomSpacing': 10
                        }
                        # 安全转换数字字段
                        try:
                            section['level'] = int(request.form.get(f'section_level_{i}', '1'))
                        except (ValueError, TypeError):
                            pass
                        try:
                            val = request.form.get(f'title_margin_{i}', '0')
                            section['margin'] = int(val) if val else 0
                        except (ValueError, TypeError):
                            pass
                        try:
                            val = request.form.get(f'title_top_spacing_{i}', '0')
                            section['topSpacing'] = int(val) if val else 0
                        except (ValueError, TypeError):
                            pass
                        try:
                            val = request.form.get(f'title_bottom_spacing_{i}', '0')
                            section['bottomSpacing'] = int(val) if val else 0
                        except (ValueError, TypeError):
                            pass
                        try:
                            val = request.form.get(f'title_height_{i}', '0')
                            section['height'] = int(val) if val else 0
                        except (ValueError, TypeError):
                            pass
                        try:
                            val = request.form.get(f'title_borderRadius_{i}', '0')
                            section['titleBorderRadius'] = int(val) if val else 0
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'image':
                        section = {
                            'type': 'image',
                            'src': request.form.get(f'section_src_{i}', ''),
                            'jump': request.form.get(f'section_jump_{i}', ''),
                            'zoomable': False,
                            'margin': 0,
                            'borderRadius': 12
                        }
                        try:
                            section['margin'] = int(request.form.get(f'image_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'image_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                        section['zoomable'] = request.form.get(f'image_zoomable_{i}') == 'on'
                    elif section_type == 'video':
                        section = {
                            'type': 'video',
                            'src': request.form.get(f'section_src_{i}', ''),
                            'poster': request.form.get(f'section_poster_{i}', ''),
                            'margin': 0,
                            'borderRadius': 12
                        }
                        try:
                            section['margin'] = int(request.form.get(f'video_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'video_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'grid':
                        images = []
                        image_count = 0
                        try:
                            image_count = int(request.form.get(f'image_count_{i}', '0'))
                        except (ValueError, TypeError):
                            image_count = 0
                        for j in range(image_count):
                            image = {
                                'src': request.form.get(f'image_src_{i}_{j}', ''),
                                'jump': request.form.get(f'image_jump_{i}_{j}', '')
                            }
                            images.append(image)
                        section = {
                            'type': 'grid',
                            'images': images,
                            'margin': 0,
                            'padding': 0,
                            'gap': 4,
                            'borderRadius': 12
                        }
                        try:
                            section['margin'] = int(request.form.get(f'grid_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['padding'] = int(request.form.get(f'grid_padding_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['gap'] = int(request.form.get(f'grid_gap_{i}') or 4)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'grid_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'carousel':
                        items = []
                        item_count = 0
                        try:
                            item_count = int(request.form.get(f'carousel_item_count_{i}', '0'))
                        except (ValueError, TypeError):
                            item_count = 0
                        for j in range(item_count):
                            item = {
                                'src': request.form.get(f'carousel_item_src_{i}_{j}', ''),
                                'title': request.form.get(f'carousel_item_title_{i}_{j}', ''),
                                'jump': request.form.get(f'carousel_item_jump_{i}_{j}', '')
                            }
                            items.append(item)
                        section = {
                            'type': 'carousel',
                            'items': items,
                            'autoplay': request.form.get(f'carousel_autoplay_{i}') == 'on',
                            'interval': 3000,
                            'margin': 20,
                            'borderRadius': 15
                        }
                        try:
                            section['interval'] = int(request.form.get(f'carousel_interval_{i}') or 3000)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['margin'] = int(request.form.get(f'carousel_spacing_{i}') or 20)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'carousel_borderRadius_{i}') or 15)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'tabs':
                        tabs = []
                        tab_count = 0
                        try:
                            tab_count = int(request.form.get(f'tabs_count_{i}', '0'))
                        except (ValueError, TypeError):
                            tab_count = 0
                        for j in range(tab_count):
                            tab = {
                                'title': request.form.get(f'tab_title_{i}_{j}', ''),
                                'sections': []
                            }
                            # 处理标签页内的区块
                            tab_section_count = 0
                            try:
                                tab_section_count = int(request.form.get(f'tab_{j}_section_count_{i}', '0'))
                            except (ValueError, TypeError):
                                tab_section_count = 0
                            for k in range(tab_section_count):
                                tab_section_type = request.form.get(f'tab_{j}_section_type_{i}_{k}')
                                if not tab_section_type:
                                    continue
                                if tab_section_type == 'title':
                                    tab_section = {
                                        'type': 'title',
                                        'level': 1,
                                        'title': request.form.get(f'tab_{j}_section_title_{i}_{k}', ''),
                                        'topSpacing': 0,
                                        'bottomSpacing': 0
                                    }
                                    try:
                                        tab_section['level'] = int(request.form.get(f'tab_{j}_section_level_{i}_{k}', '1'))
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['topSpacing'] = int(request.form.get(f'tab_{j}_title_top_spacing_{i}_{k}') or 0)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['bottomSpacing'] = int(request.form.get(f'tab_{j}_title_bottom_spacing_{i}_{k}') or 0)
                                    except (ValueError, TypeError):
                                        pass
                                elif tab_section_type == 'image':
                                    tab_section = {
                                        'type': 'image',
                                        'src': request.form.get(f'tab_{j}_section_src_{i}_{k}', ''),
                                        'jump': request.form.get(f'tab_{j}_section_jump_{i}_{k}', '')
                                    }
                                elif tab_section_type == 'video':
                                    tab_section = {
                                        'type': 'video',
                                        'src': request.form.get(f'tab_{j}_section_src_{i}_{k}', ''),
                                        'poster': request.form.get(f'tab_{j}_section_poster_{i}_{k}', '')
                                    }
                                elif tab_section_type == 'grid':
                                    tab_images = []
                                    tab_image_count = 0
                                    try:
                                        tab_image_count = int(request.form.get(f'tab_{j}_image_count_{i}_{k}', '0'))
                                    except (ValueError, TypeError):
                                        tab_image_count = 0
                                    for l in range(tab_image_count):
                                        tab_image = {
                                            'src': request.form.get(f'tab_{j}_image_src_{i}_{k}_{l}', ''),
                                            'jump': request.form.get(f'tab_{j}_image_jump_{i}_{k}_{l}', '')
                                        }
                                        tab_images.append(tab_image)
                                    tab_section = {
                                        'type': 'grid',
                                        'images': tab_images
                                    }
                                elif tab_section_type == 'carousel':
                                    tab_items = []
                                    tab_item_count = 0
                                    try:
                                        tab_item_count = int(request.form.get(f'tab_{j}_carousel_item_count_{i}_{k}', '0'))
                                    except (ValueError, TypeError):
                                        tab_item_count = 0
                                    for l in range(tab_item_count):
                                        tab_item = {
                                            'src': request.form.get(f'tab_{j}_carousel_item_src_{i}_{k}_{l}', ''),
                                            'title': request.form.get(f'tab_{j}_carousel_item_title_{i}_{k}_{l}', ''),
                                            'jump': request.form.get(f'tab_{j}_carousel_item_jump_{i}_{k}_{l}', '')
                                        }
                                        tab_items.append(tab_item)
                                    tab_section = {
                                        'type': 'carousel',
                                        'items': tab_items,
                                        'autoplay': False,
                                        'interval': 3000,
                                        'margin': 0,
                                        'borderRadius': 12
                                    }
                                    try:
                                        tab_section['autoplay'] = request.form.get(f'tab_{j}_carousel_autoplay_{i}_{k}') == 'on'
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['interval'] = int(request.form.get(f'tab_{j}_carousel_interval_{i}_{k}') or 3000)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['margin'] = int(request.form.get(f'tab_{j}_carousel_spacing_{i}_{k}') or 0)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['borderRadius'] = int(request.form.get(f'tab_{j}_carousel_borderRadius_{i}_{k}') or 12)
                                    except (ValueError, TypeError):
                                        pass
                                elif tab_section_type == 'iconRow':
                                    tab_icons = []
                                    tab_icon_count = 0
                                    try:
                                        tab_icon_count = int(request.form.get(f'tab_{j}_icon_count_{i}_{k}', '0'))
                                    except (ValueError, TypeError):
                                        tab_icon_count = 0
                                    for l in range(tab_icon_count):
                                        tab_icon = {
                                            'src': request.form.get(f'tab_{j}_icon_src_{i}_{k}_{l}', ''),
                                            'name': request.form.get(f'tab_{j}_icon_name_{i}_{k}_{l}', ''),
                                            'jump': request.form.get(f'tab_{j}_icon_jump_{i}_{k}_{l}', '')
                                        }
                                        tab_icons.append(tab_icon)
                                    tab_section = {
                                        'type': 'iconRow',
                                        'icons': tab_icons,
                                        'scale': 1.0
                                    }
                                    try:
                                        tab_section['scale'] = float(request.form.get(f'tab_{j}_icon_scale_{i}_{k}') or 1.0)
                                    except (ValueError, TypeError):
                                        pass
                                elif tab_section_type == 'imageButton':
                                    tab_buttons = []
                                    tab_button_count = 0
                                    try:
                                        tab_button_count = int(request.form.get(f'tab_{j}_imagebutton_count_{i}_{k}', '0'))
                                    except (ValueError, TypeError):
                                        tab_button_count = 0
                                    for l in range(tab_button_count):
                                        positions_str = request.form.get(f'tab_{j}_imagebutton_button_positions_{i}_{k}_{l}', '')
                                        positions = []
                                        if positions_str:
                                            try:
                                                positions = [int(p) for p in positions_str.split(',') if p.strip()]
                                            except (ValueError, TypeError):
                                                pass
                                        button = {
                                            'positions': positions,
                                            'position': 0,
                                            'span': '1x1',
                                            'text': request.form.get(f'tab_{j}_imagebutton_button_text_{i}_{k}_{l}', ''),
                                            'bgImage': request.form.get(f'tab_{j}_imagebutton_button_bgImage_{i}_{k}_{l}', ''),
                                            'jump': request.form.get(f'tab_{j}_imagebutton_button_jump_{i}_{k}_{l}', '')
                                        }
                                        try:
                                            button['position'] = int(request.form.get(f'tab_{j}_imagebutton_button_position_{i}_{k}_{l}', '0'))
                                        except (ValueError, TypeError):
                                            pass
                                        button['span'] = request.form.get(f'tab_{j}_imagebutton_button_span_{i}_{k}_{l}', '1x1')
                                        try:
                                            button['borderRadius'] = int(request.form.get(f'tab_{j}_imagebutton_button_borderRadius_{i}_{k}_{l}') or 8)
                                        except (ValueError, TypeError):
                                            button['borderRadius'] = 8
                                        try:
                                            button['fontSize'] = int(request.form.get(f'tab_{j}_imagebutton_button_fontSize_{i}_{k}_{l}') or 14)
                                        except (ValueError, TypeError):
                                            button['fontSize'] = 14
                                        tab_buttons.append(button)
                                    tab_section = {
                                        'type': 'imageButton',
                                        'src': request.form.get(f'tab_{j}_imagebutton_src_{i}_{k}', ''),
                                        'buttons': tab_buttons
                                    }
                                    try:
                                        tab_section['margin'] = int(request.form.get(f'tab_{j}_imagebutton_margin_{i}_{k}') or 0)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['borderRadius'] = int(request.form.get(f'tab_{j}_imagebutton_borderRadius_{i}_{k}') or 12)
                                    except (ValueError, TypeError):
                                        pass
                                elif tab_section_type == 'imageGridLink':
                                    links_str = request.form.get(f'tab_{j}_imagegridlink_links_{i}_{k}', '{}')
                                    links = {}
                                    try:
                                        links = json.loads(links_str)
                                    except (ValueError, TypeError, json.JSONDecodeError):
                                        links = {}
                                    tab_section = {
                                        'type': 'imageGridLink',
                                        'src': request.form.get(f'tab_{j}_imagegridlink_src_{i}_{k}', ''),
                                        'links': links
                                    }
                                    try:
                                        tab_section['gridSize'] = int(request.form.get(f'tab_{j}_imagegridlink_gridSize_{i}_{k}') or 3)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['padding'] = int(request.form.get(f'tab_{j}_imagegridlink_padding_{i}_{k}') or 10)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['gap'] = int(request.form.get(f'tab_{j}_imagegridlink_gap_{i}_{k}') or 2)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['margin'] = int(request.form.get(f'tab_{j}_imagegridlink_margin_{i}_{k}') or 0)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['borderRadius'] = int(request.form.get(f'tab_{j}_imagegridlink_borderRadius_{i}_{k}') or 12)
                                    except (ValueError, TypeError):
                                        pass
                                elif tab_section_type == 'mapping':
                                    ref_uids = request.form.getlist(f'tab_{j}_mapping_refUid_{i}_{k}')
                                    ref_uids = [u for piece in ref_uids if piece and piece.strip()
                                                for u in str(piece).replace(',', ' ').split() if u.strip()]
                                    tab_section = {
                                        'type': 'mapping',
                                        'refUids': ref_uids,
                                        'margin': 0,
                                        'borderRadius': 0
                                    }
                                    if ref_uids:
                                        tab_section['refUid'] = ref_uids[0]
                                    try:
                                        tab_section['margin'] = int(request.form.get(f'tab_{j}_mapping_margin_{i}_{k}') or 0)
                                    except (ValueError, TypeError):
                                        pass
                                    try:
                                        tab_section['borderRadius'] = int(request.form.get(f'tab_{j}_mapping_borderRadius_{i}_{k}') or 0)
                                    except (ValueError, TypeError):
                                        pass
                                else:
                                    continue
                                # 保留 tab 内组件的唯一ID（前端隐藏字段，缺失则自动生成）
                                tab_uid = request.form.get(f'tab_{j}_section_uid_{i}_{k}', '').strip()
                                if tab_uid:
                                    tab_section['uid'] = tab_uid
                                elif 'uid' not in tab_section:
                                    tab_section['uid'] = 'sec_' + uuid.uuid4().hex[:12]
                                tab['sections'].append(tab_section)
                            tabs.append(tab)
                        section = {
                            'type': 'tabs',
                            'tabs': tabs,
                            'margin': 0,
                            'tabGap': 8,
                            'borderRadius': 12
                        }
                        try:
                            section['margin'] = int(request.form.get(f'tabs_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['tabGap'] = int(request.form.get(f'tabs_gap_{i}') or 8)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'tabs_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'iconRow':
                        icons = []
                        icon_count = 0
                        try:
                            icon_count = int(request.form.get(f'icon_count_{i}', '0'))
                        except (ValueError, TypeError):
                            icon_count = 0
                        for j in range(icon_count):
                            icon = {
                                'src': request.form.get(f'icon_src_{i}_{j}', ''),
                                'name': request.form.get(f'icon_name_{i}_{j}', ''),
                                'jump': request.form.get(f'icon_jump_{i}_{j}', '')
                            }
                            icons.append(icon)
                        section = {
                            'type': 'iconRow',
                            'icons': icons,
                            'scale': 1.0,
                            'margin': 0,
                            'borderRadius': 12
                        }
                        try:
                            section['scale'] = float(request.form.get(f'icon_scale_{i}') or 1.0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['margin'] = int(request.form.get(f'iconRow_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'iconRow_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'contact':
                        section = {
                            'type': 'contact',
                            'customBgImage': request.form.get(f'contact_customBgImage_{i}', ''),
                            'name': request.form.get(f'contact_name_{i}', ''),
                            'mobilePhone': request.form.get(f'contact_mobilePhone_{i}', ''),
                            'hideButtons': request.form.get(f'contact_hideButtons_{i}') == 'on',
                            'btn1Jump': request.form.get(f'contact_btn1Jump_{i}', ''),
                            'btn1Text': request.form.get(f'contact_btn1Text_{i}', ''),
                            'btnColor': request.form.get(f'contact_btnColor_{i}', ''),
                            'btnTextColor': request.form.get(f'contact_btnTextColor_{i}', ''),
                            'btnFontSize': 24,
                            'btnGap': 10,
                            'btnOpacity': 1.0,
                            'btnTextOpacity': 1.0,
                            'btnFontWeight': 700,
                            'btnHeight': 0,
                            'btnWidthPercent': 100,
                            'btnRadius': 30,
                            'btnTop': 165,
                            'btnTopPercent': 30
                        }
                        try:
                            section['btnFontSize'] = int(request.form.get(f'contact_btnFontSize_{i}') or 24)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnGap'] = int(request.form.get(f'contact_btnGap_{i}') or 10)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnOpacity'] = float(request.form.get(f'contact_btnOpacity_{i}') or 1.0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnTextOpacity'] = float(request.form.get(f'contact_btnTextOpacity_{i}') or 1.0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnFontWeight'] = int(request.form.get(f'contact_btnFontWeight_{i}') or 700)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnHeight'] = int(request.form.get(f'contact_btnHeight_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnWidthPercent'] = float(request.form.get(f'contact_btnWidthPercent_{i}') or 100)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnRadius'] = int(request.form.get(f'contact_btnRadius_{i}') or 30)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnTop'] = int(request.form.get(f'contact_btnTop_{i}') or 165)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['btnTopPercent'] = float(request.form.get(f'contact_btnTopPercent_{i}') or 30)
                        except (ValueError, TypeError):
                            pass
                        # 若提交了百分比，同步计算一个兼容的 btnTop 像素值（375px 参考）
                        if 'btnTopPercent' in section:
                            try:
                                ratio = get_image_ratio(section.get('customBgImage')) or 1.8
                                section['btnTop'] = int(section['btnTopPercent'] / 100 * (375 / ratio))
                            except (ValueError, TypeError):
                                pass
                    elif section_type == 'mdContact':
                        section = {
                            'type': 'mdContact',
                            'bgTheme': request.form.get(f'mdContact_bgTheme_{i}', 'theme-purple-pink'),
                            'customColor': request.form.get(f'mdContact_customColor_{i}', '#ffffff'),
                            'customBgImage': request.form.get(f'mdContact_customBgImage_{i}', ''),
                            'alignment': request.form.get(f'mdContact_alignment_{i}', 'left'),
                            'name': request.form.get(f'mdContact_name_{i}', ''),
                            'title': request.form.get(f'mdContact_title_{i}', ''),
                            'phone': request.form.get(f'mdContact_phone_{i}', ''),
                            'company': request.form.get(f'mdContact_company_{i}', ''),
                            'address': request.form.get(f'mdContact_address_{i}', ''),
                            'email': request.form.get(f'mdContact_email_{i}', ''),
                            'margin': 0,
                            'borderRadius': 16,
                            'noBorder': False
                        }
                        try:
                            section['borderRadius'] = int(request.form.get(f'mdContact_borderRadius_{i}') or 16)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['margin'] = int(request.form.get(f'mdContact_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        section['noBorder'] = request.form.get(f'mdContact_noBorder_{i}') == 'on'
                    elif section_type == 'notice':
                        section = {
                            'type': 'notice',
                            'title': request.form.get(f'notice_title_{i}', ''),
                            'content': request.form.get(f'notice_content_{i}', ''),
                            'tag': request.form.get(f'notice_tag_{i}', ''),
                            'autoPopup': request.form.get(f'notice_autoPopup_{i}') == 'on',
                            'margin': 0,
                            'borderRadius': 12
                        }
                        try:
                            section['margin'] = int(request.form.get(f'notice_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'notice_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'code':
                        section = {
                            'type': 'code',
                            'content': request.form.get(f'code_content_{i}', ''),
                            'margin': 0
                        }
                        try:
                            section['margin'] = int(request.form.get(f'code_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'spacer':
                        section = {
                            'type': 'spacer',
                            'height': 20
                        }
                        try:
                            section['height'] = int(request.form.get(f'spacer_height_{i}') or 20)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'pdf':
                        section = {
                            'type': 'pdf',
                            'src': request.form.get(f'pdf_src_{i}', ''),
                            'height': 600,
                            'margin': 0
                        }
                        try:
                            section['height'] = int(request.form.get(f'pdf_height_{i}') or 600)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['margin'] = int(request.form.get(f'pdf_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'imageButton':
                        buttons = []
                        button_count = 0
                        try:
                            button_count = int(request.form.get(f'imageButton_button_count_{i}', '0'))
                        except (ValueError, TypeError):
                            button_count = 0
                        for j in range(button_count):
                            positions_str = request.form.get(f'imageButton_button_positions_{i}_{j}', '')
                            positions = []
                            if positions_str:
                                try:
                                    positions = list(map(int, positions_str.split(',')))
                                except (ValueError, TypeError):
                                    positions = []
                            
                            button = {
                                'position': int(request.form.get(f'imageButton_button_position_{i}_{j}', '0')),
                                'span': request.form.get(f'imageButton_button_span_{i}_{j}', '1x1'),
                                'positions': positions,
                                'text': request.form.get(f'imageButton_button_text_{i}_{j}', ''),
                                'bgImage': request.form.get(f'imageButton_button_bgImage_{i}_{j}', ''),
                                'color': request.form.get(f'imageButton_button_color_{i}_{j}', '#4299e1'),
                                'textColor': request.form.get(f'imageButton_button_textColor_{i}_{j}', '#ffffff'),
                                'jump': request.form.get(f'imageButton_button_jump_{i}_{j}', ''),
                                'borderRadius': 8,
                                'fontSize': 14
                            }
                            try:
                                button['borderRadius'] = int(request.form.get(f'imageButton_button_borderRadius_{i}_{j}') or 8)
                            except (ValueError, TypeError):
                                button['borderRadius'] = 8
                            try:
                                button['fontSize'] = int(request.form.get(f'imageButton_button_fontSize_{i}_{j}') or 14)
                            except (ValueError, TypeError):
                                button['fontSize'] = 14
                            buttons.append(button)
                        section = {
                            'type': 'imageButton',
                            'src': request.form.get(f'imageButton_src_{i}', ''),
                            'buttons': buttons,
                            'margin': 0,
                            'borderRadius': 12
                        }
                        try:
                            section['margin'] = int(request.form.get(f'imageButton_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'imageButton_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'imageGridLink':
                        links_str = request.form.get(f'imageGridLink_links_{i}', '{}')
                        links = {}
                        try:
                            links = json.loads(links_str)
                        except (ValueError, TypeError):
                            links = {}
                        section = {
                            'type': 'imageGridLink',
                            'src': request.form.get(f'imageGridLink_src_{i}', ''),
                            'gridSize': 3,
                            'padding': 10,
                            'gap': 2,
                            'links': links,
                            'margin': 0,
                            'borderRadius': 12
                        }
                        try:
                            section['gridSize'] = int(request.form.get(f'imageGridLink_gridSize_{i}') or 3)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['padding'] = int(request.form.get(f'imageGridLink_padding_{i}') or 10)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['gap'] = int(request.form.get(f'imageGridLink_gap_{i}') or 2)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['margin'] = int(request.form.get(f'imageGridLink_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'imageGridLink_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'footer':
                        section = {
                            'type': 'footer',
                            'text': request.form.get(f'footer_text_{i}', ''),
                            'margin': 0
                        }
                        try:
                            section['margin'] = int(request.form.get(f'footer_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                    elif section_type == 'mapping':
                        # 映射组件：支持多个有序引用ID（新增类型，不影响其他类型）
                        ref_uids = request.form.getlist(f'mapping_refUid_{i}')
                        # 拆分每个输入框中的空格/逗号分隔值，保证存为独立UID数组
                        ref_uids = [u for piece in ref_uids if piece and piece.strip()
                                    for u in str(piece).replace(',', ' ').split() if u.strip()]
                        section = {
                            'type': 'mapping',
                            'refUids': ref_uids,
                            'margin': 0,
                            'borderRadius': 0
                        }
                        if ref_uids:
                            section['refUid'] = ref_uids[0]
                        try:
                            section['margin'] = int(request.form.get(f'mapping_margin_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'mapping_borderRadius_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                    else:
                        print(f"跳过区块 {i}: 未知类型 {section_type}")
                        continue
                    
                    # 保留组件唯一ID（前端隐藏字段传入，缺失则自动生成）——仅新增字段
                    uid = request.form.get(f'section_uid_{i}', '').strip()
                    if uid:
                        section['uid'] = uid
                    elif 'uid' not in section:
                        section['uid'] = 'sec_' + uuid.uuid4().hex[:12]

                    # 添加模块级背景设置
                    bg_theme = request.form.get(f'section_bgTheme_{i}', '')
                    custom_bg_color = request.form.get(f'section_customBgColor_{i}', '')
                    custom_bg_image = request.form.get(f'section_customBgImage_{i}', '')
                    if bg_theme:
                        section['bgTheme'] = bg_theme
                    if custom_bg_color and custom_bg_color != '#ffffff':
                        section['customBgColor'] = custom_bg_color
                    if custom_bg_image:
                        section['customBgImage'] = custom_bg_image

                    # 保存自定义标题和备注
                    custom_title = request.form.get(f'section_customTitle_{i}', '').strip()
                    note = request.form.get(f'section_note_{i}', '').strip()
                    if custom_title:
                        section['customTitle'] = custom_title
                    if note:
                        section['note'] = note

                    sections.append(section)
                    print(f"添加区块: {section}")
                except Exception as e:
                    print(f"处理区块 {i} 时出错: {e}")
                    # 单个区块出错不影响其他区块继续处理
                    continue

            # 安全检查：只有当 section_count > 0 时才覆盖 sections
            # （section_count = 0 可能表示表单没传 sections 字段，仅修改了 page-level 字段如背景图）
            if section_count > 0:
                page['sections'] = sections
            else:
                print(f"section_count=0, 跳过 sections 覆盖（保留原有 {len(page.get('sections', []))} 个 sections）")
            save_config(config)
            print(f"保存配置成功")
            flash('内容区块保存成功')
            return redirect(url_for('pages'))
        except Exception as e:
            print(f"保存配置时出错: {e}")
            import traceback
            print(traceback.format_exc())
            flash(f'保存失败: {e}')
            return redirect(url_for('edit_page_sections', page_id=page_id))
    
    sections = page.get('sections', [])
    for section in sections:
        if section['type'] == 'image' and 'zoomable' not in section:
            section['zoomable'] = False
        if section['type'] == 'image' and 'margin' not in section:
            section['margin'] = 0
        if section['type'] == 'image' and 'borderRadius' not in section:
            section['borderRadius'] = 12

    # 构建当前页面组件索引（供映射组件/批量复制参考）
    component_options = []
    ensure_section_uids(config)
    for psec in page.get('sections', []):
        component_options.append({
            'uid': psec.get('uid', ''),
            'pageId': page.get('id', ''),
            'pageTitle': page.get('title', ''),
            'type': psec.get('type', ''),
            'customTitle': psec.get('customTitle', '')
        })
    return render_template('edit_sections.html', page=page, page_id=page_id, sections=sections,
                           component_options=component_options)

# 上传资源
@app.route('/admin/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Debug logging
        print(f"Upload request received")
        print(f"Files in request: {list(request.files.keys())}")
        
        # Check if files are present in request (support both 'file' and 'files')
        uploaded_files = []
        if 'files' in request.files:
            # Handle multiple files
            for f in request.files.getlist('files'):
                uploaded_files.append(f)
        elif 'file' in request.files:
            # Handle single file
            uploaded_files.append(request.files['file'])
        
        if not uploaded_files:
            print("ERROR: No files in request")
            return jsonify({'success': False, 'message': '没有文件上传'})
        
        results = []
        for file in uploaded_files:
            print(f"File object: {file}")
            print(f"File filename: {file.filename}")
            
            original_filename = file.filename or ''
            
            # Check if file has a name
            if not original_filename:
                print("ERROR: Empty filename")
                continue
            
            # Validate and save the file
            if file and allowed_file(original_filename):
                try:
                    # Get file extension
                    ext = os.path.splitext(original_filename)[1].lower()
                    print(f"File extension: {ext}")
                    
                    # Generate random filename: timestamp + UUID + extension
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    random_str = str(uuid.uuid4().hex)[:8]
                    filename = f"{timestamp}_{random_str}{ext}"
                    print(f"Generated filename: {filename}")
                    
                    # Ensure upload directory exists
                    upload_folder = app.config['UPLOAD_FOLDER']
                    print(f"Upload folder: {upload_folder}")
                    
                    if not os.path.exists(upload_folder):
                        print(f"Creating upload folder: {upload_folder}")
                        os.makedirs(upload_folder)
                    
                    # Save the file
                    filepath = os.path.join(upload_folder, filename)
                    print(f"Saving file to: {filepath}")
                    file.save(filepath)
                    print(f"File saved successfully, size: {os.path.getsize(filepath)}")
                    
                    # Generate file URL
                    file_url = f"uploads/{filename}"
                    print(f"File URL: {file_url}")

                    result = {
                        'originalName': original_filename,
                        'url': file_url
                    }

                    # 如果有target_size参数，自动压缩
                    target_size = request.form.get('target_size')
                    ext = os.path.splitext(filename)[1].lower()
                    
                    if target_size:
                        target_bytes = parse_target_size(target_size)
                        if target_bytes is not None:
                            try:
                                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.pdf']:
                                    orig_size, new_size = compress_file(filepath, target_bytes)
                                    result['compressed'] = True
                                    result['message'] = f'上传并压缩成功: {orig_size//1024}KB -> {new_size//1024}KB'
                                    print(f"Compressed: {orig_size} -> {new_size} bytes")
                            except Exception as e:
                                print(f"Compression error: {e}")
                                result['compressed'] = False
                                result['compression_error'] = str(e)
                    elif ext == '.pdf':
                        # PDF自动按大小规则压缩
                        file_size = os.path.getsize(filepath)
                        if file_size > 10 * 1024 * 1024:
                            target_bytes = 7 * 1024 * 1024
                        elif file_size > 5 * 1024 * 1024:
                            target_bytes = 3 * 1024 * 1024
                        else:
                            target_bytes = None  # <5MB保留原大小
                        
                        if target_bytes:
                            try:
                                orig_size, new_size = compress_file(filepath, target_bytes)
                                result['compressed'] = True
                                result['message'] = f'PDF自动压缩: {orig_size//1024}KB -> {new_size//1024}KB'
                                print(f"Auto-compressed PDF: {orig_size} -> {new_size} bytes")
                            except Exception as e:
                                print(f"PDF auto-compression error: {e}")

                    results.append(result)
                except Exception as e:
                    print(f"File upload error: {e}")
                    import traceback
                    traceback.print_exc()
        
        if results:
            print(f"Upload successful, {len(results)} files uploaded")
            response = {'success': True, 'paths': results}
            if any(r.get('compressed') for r in results):
                response['compressed'] = True
                response['message'] = results[0].get('message', '上传并压缩成功')
            return jsonify(response)
        else:
            print("ERROR: No files were successfully uploaded")
            return jsonify({'success': False, 'message': '文件上传失败'})
    return render_template('upload.html')

# 替换附件（保留原引用链接，直接替换文件内容）——兼容后台与前台开发者模式
@app.route('/admin/replace-resource', methods=['POST'])
@login_required
def replace_resource():
    """用新文件覆盖旧文件，保留原文件名/引用链接，所有引用自动生效

    支持的入参：
      - filename=xxx.png（后台资源列表表单）
      - link=/uploads/xxx.png 或 http://.../uploads/xxx.png（前台 dev 模式跳转）
    目标文件不存在时：自动作为新增上传处理。
    """
    raw_filename = request.form.get('filename', '').strip()
    raw_link = request.form.get('link', '').strip()

    if raw_filename:
        filename = raw_filename
    elif raw_link:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(raw_link)
        filename = os.path.basename(unquote(parsed.path))
    else:
        flash('参数不完整：需要 filename 或 link')
        return redirect(url_for('resources'))

    file = request.files.get('file')
    if not file or not file.filename:
        flash('未收到上传文件')
        return redirect(url_for('resources'))

    if '/' in filename or '\\' in filename or filename in ('.', '..') or not filename:
        flash(f'非法的文件名: {filename}')
        return redirect(url_for('resources'))

    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(filename)
    if not safe_filename:
        safe_filename = secure_filename(file.filename) or 'upload.bin'
    filename = safe_filename

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    existed = os.path.exists(filepath)

    if existed:
        orig_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'upload-orig')
        if not os.path.exists(orig_dir):
            os.makedirs(orig_dir)
        try:
            import shutil
            shutil.copy2(filepath, os.path.join(orig_dir, filename + '.bak'))
        except Exception as e:
            print(f"备份旧文件失败: {e}")

    try:
        file.save(filepath)
        action = '替换' if existed else '新增'
        flash(f'文件{action}成功，引用链接: /uploads/{filename}')
    except Exception as e:
        flash(f'保存失败: {e}')
    return redirect(url_for('resources'))

# 替换附件 API（供 AI 编排 / 前台开发者模式）
@app.route('/api/resource/replace', methods=['POST'])
def api_replace_resource():
    """用新文件覆盖旧文件，保留原引用链接

    支持的入参形式（任选其一）：
      1. filename=xxx.png + file=@新文件              （后台资源管理表单）
      2. link=/uploads/xxx.png 或 http://.../uploads/xxx.png + file=@新文件  （前台 dev 模式一键替换）
    目标文件不存在时：自动作为"新增上传"处理，不再返回 404。
    """
    # 1. 解析 filename（兼容 filename 和 link 两种入参）
    raw_filename = request.form.get('filename', '').strip()
    raw_link = request.form.get('link', '').strip()

    if raw_filename:
        filename = raw_filename
    elif raw_link:
        # 从 link 中抽取 basename（去掉 query / hash / 多级路径）
        from urllib.parse import urlparse, unquote
        parsed = urlparse(raw_link)
        basename = os.path.basename(unquote(parsed.path))
        filename = basename
    else:
        return jsonify({
            'code': 1,
            'success': False,
            'error': '参数不完整：需要 filename 或 link 任一字段，加上 file 字段'
        }), 400

    # 2. 取上传文件
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({
            'code': 1,
            'success': False,
            'error': '未收到上传文件（需要 file 字段）'
        }), 400

    # 3. 合法化文件名（去路径穿越字符）
    if '/' in filename or '\\' in filename or filename in ('.', '..') or not filename:
        return jsonify({
            'code': 1,
            'success': False,
            'error': f'非法的文件名: {filename}'
        }), 400

    # 4. 安全文件名（保留中文/Unicode，但去非法字符）
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(filename)
    if not safe_filename:
        safe_filename = secure_filename(file.filename) or 'upload.bin'
    filename = safe_filename

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    existed = os.path.exists(filepath)

    # 5. 备份旧文件（仅当文件原本存在）
    if existed:
        orig_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'upload-orig')
        if not os.path.exists(orig_dir):
            os.makedirs(orig_dir)
        try:
            import shutil
            shutil.copy2(filepath, os.path.join(orig_dir, filename + '.bak'))
        except Exception as e:
            print(f"备份旧文件失败: {e}")

    # 6. 保存新文件（覆盖或新建）
    try:
        file.save(filepath)
    except Exception as e:
        return jsonify({
            'code': 1,
            'success': False,
            'error': f'保存文件失败: {e}'
        }), 500

    action = '替换' if existed else '新增'
    return jsonify({
        'code': 0,
        'success': True,
        'url': f"{current_domain}/uploads/{filename}",
        'filename': filename,
        'existed': existed,
        'action': action,
        'message': f'文件已{action}成功，引用链接保持不变'
    })

def parse_target_size(target_size_str):
    """解析目标大小字符串为字节数"""
    target_size_str = target_size_str.strip().upper()
    try:
        if target_size_str.endswith('MB'):
            return int(float(target_size_str[:-2]) * 1024 * 1024)
        elif target_size_str.endswith('KB'):
            return int(float(target_size_str[:-2]) * 1024)
        elif target_size_str.endswith('B'):
            return int(float(target_size_str[:-1]))
        else:
            return int(target_size_str)
    except ValueError:
        return None

def compress_file(filepath, target_bytes):
    """压缩文件到目标大小，返回 (original_size, new_size) 或抛出异常"""
    ext = os.path.splitext(filepath)[1].lower()
    is_image = ext in ['.png', '.jpg', '.jpeg', '.gif']
    is_pdf = ext == '.pdf'

    if not is_image and not is_pdf:
        raise ValueError('仅支持图片和PDF文件')

    # 创建原始文件备份目录
    orig_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'upload-orig')
    if not os.path.exists(orig_dir):
        os.makedirs(orig_dir)

    # 备份原始文件
    orig_filename = os.path.basename(filepath)
    orig_filepath = os.path.join(orig_dir, orig_filename)
    if not os.path.exists(orig_filepath):
        import shutil
        shutil.copy2(filepath, orig_filepath)

    current_size = os.path.getsize(filepath)

    if is_image:
        from PIL import Image, UnidentifiedImageError
        try:
            img = Image.open(filepath)
            img.load()
        except (UnidentifiedImageError, OSError, IOError) as e:
            raise ValueError(f'图片文件损坏或格式不支持: {str(e)}')

        if img.mode in ('RGBA', 'LA', 'P', 'L'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                bg.paste(img, mask=img.split()[-1])
            else:
                bg.paste(img)
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        if current_size <= target_bytes:
            img.save(filepath, 'JPEG', quality=92, optimize=True)
            new_size = os.path.getsize(filepath)
            return (current_size, new_size)

        low, high = 10, 92
        best_quality = 85
        scale = 1.0

        for _ in range(30):
            mid = (low + high) // 2
            if scale < 1.0:
                new_w = max(1, int(img.width * scale))
                new_h = max(1, int(img.height * scale))
                resized = img.resize((new_w, new_h), Image.LANCZOS)
                resized.save(filepath, 'JPEG', quality=mid, optimize=True)
            else:
                img.save(filepath, 'JPEG', quality=mid, optimize=True)

            new_size = os.path.getsize(filepath)

            if new_size <= target_bytes:
                best_quality = mid
                low = mid + 1
            else:
                high = mid - 1

            if high < low and new_size > target_bytes:
                scale *= 0.75
                if scale < 0.25:
                    break
                low, high = 10, 92

        if scale < 1.0:
            new_w = max(1, int(img.width * scale))
            new_h = max(1, int(img.height * scale))
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            resized.save(filepath, 'JPEG', quality=best_quality, optimize=True)
        else:
            img.save(filepath, 'JPEG', quality=best_quality, optimize=True)

    elif is_pdf:
        import fitz
        import io

        doc = fitz.open(filepath)
        num_pages = len(doc)

        target_dpi = 150
        pdf_images = []

        for _ in range(5):
            pdf_images = []
            for page_num in range(num_pages):
                page = doc[page_num]
                mat = fitz.Matrix(target_dpi / 72, target_dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("jpeg")
                pdf_images.append((img_bytes, pix.width, pix.height))

            total_estimated = sum(len(b) for b, _, _ in pdf_images)
            if total_estimated <= target_bytes * 1.5 or target_dpi <= 72:
                break
            target_dpi = max(72, target_dpi - 20)

        doc.close()

        output_pdf = filepath + '.tmp'
        from PIL import Image as PILImage
        pil_images = []
        for img_bytes, w, h in pdf_images:
            pil_img = PILImage.open(io.BytesIO(img_bytes))
            pil_images.append(pil_img)

        if pil_images:
            pil_images[0].save(
                output_pdf, 'PDF',
                save_all=True,
                append_images=pil_images[1:],
                resolution=target_dpi,
                optimize=True
            )
        else:
            blank = PILImage.new('RGB', (595, 842), (255, 255, 255))
            blank.save(output_pdf, 'PDF', resolution=target_dpi)

        import shutil
        shutil.move(output_pdf, filepath)

    new_size = os.path.getsize(filepath)
    return (current_size, new_size)

# 资源管理
@app.route('/admin/resources')
@login_required
def resources():
    resources_list = []
    uploads_dir = app.config['UPLOAD_FOLDER']
    
    if os.path.exists(uploads_dir):
        for filename in os.listdir(uploads_dir):
            filepath = os.path.join(uploads_dir, filename)
            if os.path.isfile(filepath):
                # 获取文件信息
                stat = os.stat(filepath)
                size = stat.st_size
                upload_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                
                # 确定文件类型
                ext = os.path.splitext(filename)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                    file_type = 'image'
                elif ext in ['.mp4']:
                    file_type = 'video'
                elif ext in ['.pdf']:
                    file_type = 'pdf'
                else:
                    file_type = 'other'
                
                # 格式化文件大小
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.2f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.2f} MB"
                
                resources_list.append({
                    'filename': filename,
                    'url': f"{current_domain}/uploads/{filename}",
                    'type': file_type,
                    'size': size_str,
                    'upload_time': upload_time
                })
    
    return render_template('resources.html', resources=resources_list)

# 删除资源
@app.route('/admin/delete-resource', methods=['POST'])
@login_required
def delete_resource():
    filename = request.form.get('filename')
    if filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            flash('文件删除成功')
        else:
            flash('文件不存在')
    else:
        flash('文件名不能为空')
    return redirect(url_for('resources'))

def extract_referenced_files(config):
    """从配置文件中提取所有引用的附件文件名"""
    referenced_files = set()
    
    # 解析URL并提取文件名的函数
    def extract_filename(url):
        if url:
            # 移除域名部分，获取路径
            if '://' in url:
                path = url.split('://')[1].split('/')
            else:
                path = url.split('/')
            # 获取最后一部分作为文件名
            if path:
                filename = path[-1]
                # 检查是否是上传目录中的文件（不包含特殊字符）
                if filename and '/' not in filename and '\\' not in filename:
                    return filename
        return None
    
    # 扫描 basicInfo 中的 logo
    basic_info = config.get('basicInfo', {})
    logo = basic_info.get('logo')
    if logo:
        filename = extract_filename(logo)
        if filename:
            referenced_files.add(filename)
    
    # 扫描所有页面
    for page in config.get('pages', []):
        # 扫描页面的 share_icon
        share_icon = page.get('share_icon')
        if share_icon:
            filename = extract_filename(share_icon)
            if filename:
                referenced_files.add(filename)
        
        # 扫描页面中的所有区块
        for section in page.get('sections', []):
            # 扫描各种类型的区块
            if section.get('type') == 'image':
                src = section.get('src')
                if src:
                    filename = extract_filename(src)
                    if filename:
                        referenced_files.add(filename)
            elif section.get('type') == 'video':
                src = section.get('src')
                if src:
                    filename = extract_filename(src)
                    if filename:
                        referenced_files.add(filename)
                poster = section.get('poster')
                if poster:
                    filename = extract_filename(poster)
                    if filename:
                        referenced_files.add(filename)
            elif section.get('type') == 'pdf':
                src = section.get('src')
                if src:
                    filename = extract_filename(src)
                    if filename:
                        referenced_files.add(filename)
            elif section.get('type') == 'grid':
                for img in section.get('images', []):
                    src = img.get('src')
                    if src:
                        filename = extract_filename(src)
                        if filename:
                            referenced_files.add(filename)
            elif section.get('type') == 'carousel':
                for item in section.get('items', []):
                    src = item.get('src')
                    if src:
                        filename = extract_filename(src)
                        if filename:
                            referenced_files.add(filename)
            elif section.get('type') == 'tabs':
                for tab in section.get('tabs', []):
                    for tab_section in tab.get('sections', []):
                        if tab_section.get('type') == 'image':
                            src = tab_section.get('src')
                            if src:
                                filename = extract_filename(src)
                                if filename:
                                    referenced_files.add(filename)
                        elif tab_section.get('type') == 'video':
                            src = tab_section.get('src')
                            if src:
                                filename = extract_filename(src)
                                if filename:
                                    referenced_files.add(filename)
                            poster = tab_section.get('poster')
                            if poster:
                                filename = extract_filename(poster)
                                if filename:
                                    referenced_files.add(filename)
                        elif tab_section.get('type') == 'pdf':
                            src = tab_section.get('src')
                            if src:
                                filename = extract_filename(src)
                                if filename:
                                    referenced_files.add(filename)
                        elif tab_section.get('type') == 'grid':
                            for img in tab_section.get('images', []):
                                src = img.get('src')
                                if src:
                                    filename = extract_filename(src)
                                    if filename:
                                        referenced_files.add(filename)
                        elif tab_section.get('type') == 'carousel':
                            for item in tab_section.get('items', []):
                                src = item.get('src')
                                if src:
                                    filename = extract_filename(src)
                                    if filename:
                                        referenced_files.add(filename)
                        elif tab_section.get('type') == 'imageButton':
                            src = tab_section.get('src')
                            if src:
                                filename = extract_filename(src)
                                if filename:
                                    referenced_files.add(filename)
                            for button in tab_section.get('buttons', []):
                                bg_image = button.get('bgImage')
                                if bg_image:
                                    filename = extract_filename(bg_image)
                                    if filename:
                                        referenced_files.add(filename)
            elif section.get('type') == 'iconRow':
                for icon in section.get('icons', []):
                    src = icon.get('src')
                    if src:
                        filename = extract_filename(src)
                        if filename:
                            referenced_files.add(filename)
            elif section.get('type') == 'imageButton':
                src = section.get('src')
                if src:
                    filename = extract_filename(src)
                    if filename:
                        referenced_files.add(filename)
                for button in section.get('buttons', []):
                    bg_image = button.get('bgImage')
                    if bg_image:
                        filename = extract_filename(bg_image)
                        if filename:
                            referenced_files.add(filename)
            elif section.get('type') == 'title':
                logo = section.get('logo')
                if logo:
                    filename = extract_filename(logo)
                    if filename:
                        referenced_files.add(filename)
            elif section.get('type') == 'contact':
                logo = section.get('logo')
                if logo:
                    filename = extract_filename(logo)
                    if filename:
                        referenced_files.add(filename)
                customBgImage = section.get('customBgImage')
                if customBgImage:
                    filename = extract_filename(customBgImage)
                    if filename:
                        referenced_files.add(filename)
    
    return referenced_files

# 检测未引用的文件
@app.route('/admin/find-unused-files')
@login_required
def find_unused_files():
    config = load_config()
    referenced_files = extract_referenced_files(config)
    
    # 获取上传目录中的所有文件
    uploads_dir = app.config['UPLOAD_FOLDER']
    all_files = set()
    
    if os.path.exists(uploads_dir):
        for filename in os.listdir(uploads_dir):
            filepath = os.path.join(uploads_dir, filename)
            if os.path.isfile(filepath):
                all_files.add(filename)
    
    # 找出未被引用的文件
    unused_files = all_files - referenced_files
    
    # 获取未引用文件的详细信息
    unused_files_info = []
    for filename in unused_files:
        filepath = os.path.join(uploads_dir, filename)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            size = stat.st_size
            upload_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
            
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.2f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.2f} MB"
            
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                file_type = 'image'
            elif ext in ['.mp4']:
                file_type = 'video'
            elif ext in ['.pdf']:
                file_type = 'pdf'
            else:
                file_type = 'other'
            
            unused_files_info.append({
                'filename': filename,
                'url': f"{current_domain}/uploads/{filename}",
                'type': file_type,
                'size': size_str,
                'upload_time': upload_time,
                'size_bytes': size
            })
    
    # 按文件大小排序（从大到小）
    unused_files_info.sort(key=lambda x: x['size_bytes'], reverse=True)
    
    return render_template('resources.html', resources=[], unused_files=unused_files_info)

# 清理未引用的文件
@app.route('/admin/clean-unused-files', methods=['POST'])
@login_required
def clean_unused_files():
    config = load_config()
    referenced_files = extract_referenced_files(config)
    
    uploads_dir = app.config['UPLOAD_FOLDER']
    cleaned_count = 0
    cleaned_size = 0
    
    if os.path.exists(uploads_dir):
        for filename in os.listdir(uploads_dir):
            filepath = os.path.join(uploads_dir, filename)
            if os.path.isfile(filepath) and filename not in referenced_files:
                try:
                    file_size = os.path.getsize(filepath)
                    os.remove(filepath)
                    cleaned_count += 1
                    cleaned_size += file_size
                    print(f"Deleted unused file: {filename}")
                except Exception as e:
                    print(f"Failed to delete {filename}: {e}")
    
    # 格式化清理的大小
    if cleaned_size < 1024:
        size_str = f"{cleaned_size} B"
    elif cleaned_size < 1024 * 1024:
        size_str = f"{cleaned_size / 1024:.2f} KB"
    else:
        size_str = f"{cleaned_size / (1024 * 1024):.2f} MB"
    
    flash(f'已清理 {cleaned_count} 个未引用文件，释放空间 {size_str}')
    return redirect(url_for('find_unused_files'))

# 图片查看页面（支持自适应缩放）
@app.route('/view/<filename>')
def view_image(filename):
    return render_template('image_viewer.html', filename=filename)

# PDF查看页面
@app.route('/pdf/<filename>')
def view_pdf(filename):
    return render_template('pdf_viewer.html', filename=filename)

# 静态文件服务
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    import os
    print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    print(f"File path: {filepath}")
    print(f"File exists: {os.path.exists(filepath)}")
    
    # 获取文件扩展名
    ext = os.path.splitext(filename)[1].lower()
    
    # 如果是图片文件，检查是否是浏览器直接访问
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
    if ext in image_extensions and os.path.exists(filepath):
        # 检查请求头，判断是否是浏览器直接访问
        accept_header = request.headers.get('Accept', '')
        # 如果是浏览器直接访问（Accept包含text/html），重定向到查看页面
        if 'text/html' in accept_header:
            return redirect(f'/view/{filename}')
    
    # 如果是PDF文件，重定向到PDF查看页面
    if ext == '.pdf' and os.path.exists(filepath):
        accept_header = request.headers.get('Accept', '')
        if 'text/html' in accept_header:
            return redirect(f'/pdf/{filename}')
    
    if os.path.exists(filepath):
        from flask import send_file
        return send_file(filepath)
    else:
        # 尝试使用绝对路径
        abs_path = os.path.join(os.path.dirname(__file__), '..', 'uploads', filename)
        print(f"Absolute path: {abs_path}")
        print(f"Absolute path exists: {os.path.exists(abs_path)}")
        if os.path.exists(abs_path):
            from flask import send_file
            return send_file(abs_path)
        else:
            return 'File not found', 404

# 根路径使用动态模板
@app.route('/')
def index():
    """根路径使用动态模板"""
    return index_dynamic()

# 静态文件服务 - 提供H5页面
@app.route('/index-dynamic.html')
def index_dynamic():
    """提供H5动态页面"""
    # 开发者模式需要 token 验证
    dev_mode = request.args.get('dev') == '1'
    if dev_mode:
        token = request.args.get('token', '')
        valid_token = 'wswwsw1234'
        if token != valid_token:
            return render_template('access_denied.html'), 403
    
    config = load_config()
    
    # 获取分享设置
    share_title = ''
    share_desc = ''
    share_icon = ''
    
    # 获取页面参数
    page_id = request.args.get('page')
    
    if page_id:
        # 从指定页面获取分享设置
        for page in config.get('pages', []):
            if page['id'] == page_id:
                share_title = page.get('share_title', '')
                share_desc = page.get('share_desc', '')
                share_icon = page.get('share_icon', '')
                break
    else:
        # 从默认页面获取分享设置
        default_page_id = config.get('settings', {}).get('defaultPage', 'home')
        for page in config.get('pages', []):
            if page['id'] == default_page_id:
                share_title = page.get('share_title', '')
                share_desc = page.get('share_desc', '')
                share_icon = page.get('share_icon', '')
                break
    
    # 如果没有配置分享图标，尝试从名片信息中获取
    if not share_icon:
        contact_section = None
        # 查找名片信息区块
        for page in config.get('pages', []):
            for section in page.get('sections', []):
                if section.get('type') == 'contact':
                    contact_section = section
                    break
            if contact_section:
                break
        if contact_section:
            share_icon = contact_section.get('logo', '')
        elif config.get('basicInfo', {}).get('logo'):
            share_icon = config.get('basicInfo', {}).get('logo', '')
    
    return render_template('index-dynamic.html', share_title=share_title, share_desc=share_desc, share_icon=share_icon, current_domain=current_domain)

# 静态文件服务 - 提供JS文件
@app.route('/js/<path:filename>')
def static_js(filename):
    """提供JS静态文件"""
    import os
    js_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'js', filename)
    if os.path.exists(js_file):
        from flask import send_file
        return send_file(js_file)
    else:
        return 'File not found', 404

# 静态文件服务 - 提供CSS文件
@app.route('/css/<path:filename>')
def static_css(filename):
    """提供CSS静态文件"""
    import os
    css_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'css', filename)
    if os.path.exists(css_file):
        from flask import send_file
        return send_file(css_file)
    else:
        return 'File not found', 404

# PWA 文件服务
@app.route('/manifest.json')
def serve_manifest():
    """提供 PWA manifest.json"""
    manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'manifest.json')
    if os.path.exists(manifest_path):
        return send_file(manifest_path, mimetype='application/manifest+json')
    return 'Not found', 404

@app.route('/sw.js')
def serve_sw():
    """提供 Service Worker"""
    sw_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sw.js')
    if os.path.exists(sw_path):
        return send_file(sw_path, mimetype='application/javascript')
    return 'Not found', 404

@app.route('/favicon-192.png')
def serve_favicon_192():
    """提供 PWA 图标 192x192"""
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'favicon-192.png')
    if os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/png')
    return 'Not found', 404

@app.route('/favicon-512.png')
def serve_favicon_512():
    """提供 PWA 图标 512x512"""
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'favicon-512.png')
    if os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/png')
    return 'Not found', 404

# Pages 独立页面服务
@app.route('/pages/<page_name>/')
def serve_page(page_name):
    """提供 pages 目录下的独立页面"""
    page_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages', page_name)
    index_file = os.path.join(page_dir, 'index.html')
    
    if os.path.exists(index_file):
        return send_file(index_file)
    return 'Page not found', 404

@app.route('/pages/<page_name>/<path:filename>')
def serve_page_static(page_name, filename):
    """提供 pages 目录下的静态资源"""
    page_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages', page_name)
    return send_from_directory(page_dir, filename)

# API接口
@app.route('/api/wechat-sign', methods=['GET'])
def wechat_sign():
    """获取微信签名"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': '缺少url参数'}), 400
    
    sign_data = generate_signature(url)
    if sign_data:
        return jsonify(sign_data)
    else:
        return jsonify({'error': '生成签名失败'}), 500

@app.route('/api/contact-vcard', methods=['GET'])
def contact_vcard():
    """生成联系人 vCard 文件（.vcf），手机系统/微信会弹出「保存到通讯录」面板"""
    from flask import Response
    config = load_config()
    page_id = request.args.get('page')

    page = None
    if page_id:
        for p in config.get('pages', []):
            if p['id'] == page_id:
                page = p
                break
    else:
        default_page_id = config.get('settings', {}).get('defaultPage', 'home')
        for p in config.get('pages', []):
            if p['id'] == default_page_id:
                page = p
                break

    contact_section = None
    if page:
        for sec in page.get('sections', []):
            if sec.get('type') == 'contact':
                contact_section = sec
                break

    basic_info = config.get('basicInfo', {})
    info = {**basic_info, **(contact_section or {})}

    name = info.get('name', '') or ''
    phone = info.get('mobilePhone', '') or info.get('phone', '') or ''

    vcard = []
    vcard.append('BEGIN:VCARD')
    vcard.append('VERSION:3.0')
    vcard.append(f'N:{name};;;')
    vcard.append(f'FN:{name}')
    if phone:
        vcard.append(f'TEL;TYPE=CELL:{phone}')
    if info.get('company'):
        vcard.append(f'ORG:{info["company"]}')
    if info.get('title'):
        vcard.append(f'TITLE:{info["title"]}')
    if info.get('email'):
        vcard.append(f'EMAIL;TYPE=INTERNET:{info["email"]}')
    if info.get('address'):
        vcard.append(f'ADR;TYPE=WORK:;;{info["address"]};;;;')
    if name or phone:
        vcard.append('NOTE:来自微信名片')
    vcard.append('END:VCARD')

    content = '\r\n'.join(vcard) + '\r\n'
    # 关键：无论 iOS 还是 Android，都不用 attachment（attachment 会触发下载/跳浏览器）。
    # 统一用 inline：iOS 微信 QuickLook 直接弹「添加到通讯录」；
    # Android 微信/系统 WebView 对 text/x-vcard 会调用系统 intent，弹出「打开方式」
    # 选择通讯录/联系人应用，进而弹出「保存到通讯录」。
    import urllib.parse as _up
    filename = 'contact.vcf'
    quoted_name = _up.quote(name or 'contact')
    headers = {'Content-Disposition': f'inline; filename="{filename}"; filename*=UTF-8\'\'{quoted_name}.vcf'}
    return Response(
        content,
        mimetype='text/x-vcard; charset=utf-8',
        headers=headers
    )

@app.route('/api/card-config', methods=['GET'])
def card_config():
    """获取名片配置"""
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    # 获取页面参数
    page_id = request.args.get('page')
    
    page_found = False
    if page_id:
        # 返回指定页面的配置
        for page in config['pages']:
            if page['id'] == page_id:
                config['currentPage'] = page
                page_found = True
                break

        # 如果页面不存在：①若该 pageId 与 defaultPage 不同，自动降级到 defaultPage；
        #                ②若仍找不到，再返回占位对象（不让 dev 模式编辑后丢失）
        if not page_found:
            fallback_id = config.get('settings', {}).get('defaultPage', 'home')
            if fallback_id and fallback_id != page_id:
                for page in config['pages']:
                    if page['id'] == fallback_id:
                        config['currentPage'] = page
                        page_found = True
                        break
            if not page_found:
                config['currentPage'] = {
                    'id': page_id,
                    'title': page_id,
                    'groupId': 'default',
                    'sections': [
                        {'type': 'title', 'level': 1, 'title': f'页面 {page_id} 待创建（首次保存自动建）'}
                    ],
                    '_placeholder': True
                }
    else:
        # 返回默认页面
        default_page_id = config.get('settings', {}).get('defaultPage', 'home')
        for page in config['pages']:
            if page['id'] == default_page_id:
                config['currentPage'] = page
                break
    
    # 解析映射组件（仅展开 mapping 类型，非 mapping 组件原样返回，不影响原有展示）
    config = resolve_all_mappings(config)
    
    # 添加当前域名信息
    config['currentDomain'] = current_domain
    return jsonify(config)

@app.route('/api/update-page', methods=['POST'])
def update_page():
    """更新页面信息。

    兼容历史行为：
      - 若 pageId 已存在 → 直接更新该页面字段
      - 若 pageId 不存在 → 自动作为新增页面创建（解决"前台默认 page=home 但
        card_config.json 里没有 home 页 → 用户在 dev 模式下编辑 → 后端 404 →
        看上去改动不生效"的问题）
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效的数据'}), 400

    page_id = data.get('pageId')
    if not page_id:
        return jsonify({'error': '缺少页面ID'}), 400

    # 防止 pageId 里掺路径分隔符 / 特殊字符
    if '/' in page_id or '\\' in page_id or page_id in ('.', '..'):
        return jsonify({'error': f'非法的页面ID: {page_id}'}), 400

    config = load_config()
    if 'pages' not in config:
        config['pages'] = []

    # 查找页面
    page = None
    for p in config['pages']:
        if p.get('id') == page_id:
            page = p
            break

    is_new = False
    if not page:
        # 自动创建占位页面（解决"开发者模式下改动不生效"的核心修复点）
        is_new = True
        page = {
            'id': page_id,
            'title': page_id,
            'groupId': data.get('groupId') or 'default',
            'sections': [],
            'create_time': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
            'auto_created': True
        }
        config['pages'].append(page)
        # 兜底：保证 groups / settings 存在
        if 'groups' not in config:
            config['groups'] = [{'id': 'default', 'name': '默认分组', 'description': '默认页面分组'}]
        if 'settings' not in config:
            config['settings'] = {'showCallConfirm': True, 'defaultPage': page_id}

    # 更新允许的字段（增量）
    if 'title' in data:
        page['title'] = data['title']
    if 'groupId' in data and data['groupId']:
        page['groupId'] = data['groupId']
    if 'share_title' in data:
        page['share_title'] = data['share_title']
    if 'share_desc' in data:
        page['share_desc'] = data['share_desc']
    if 'share_icon' in data:
        page['share_icon'] = data['share_icon']

    # 更新最近修改时间
    import datetime as _dt
    page['update_time'] = _dt.datetime.now().isoformat(timespec='seconds')

    save_config(config)
    return jsonify({
        'success': True,
        'message': '页面已新增并保存' if is_new else '页面更新成功',
        'is_new': is_new,
        'page': {
            'id': page.get('id'),
            'title': page.get('title'),
            'share_title': page.get('share_title'),
            'share_desc': page.get('share_desc'),
            'groupId': page.get('groupId')
        }
    })

# 批量设置页面展示文本与 Logo（纯新增接口，不修改原有逻辑）
# 请求体示例：
# {
#   "pages": [
#     {
#       "pageId": "wangli",
#       "page": { "title": "页面标题", "share_title": "分享标题", "share_desc": "分享描述", "share_icon": "分享图标URL" },
#       "contact": { "name": "姓名", "title": "职位/单位", "title2": "职位2", "phone": "电话", "mobilePhone": "手机号",
#                    "email": "邮箱", "company": "公司", "address": "地址", "logo": "Logo URL", "customBgImage": "背景图URL" }
#     }
#   ]
# }
# 说明：
# - page 段设置页面级展示字段；contact 段设置该页面名片信息区块的展示字段
# - 仅更新传入的字段，未传字段保持不变；找不到页面/区块时跳过并在 results 中提示
@app.route('/api/pages/batch-display', methods=['POST'])
def api_pages_batch_display():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or 'pages' not in data:
        return jsonify({'success': False, 'error': '缺少 pages 数组'}), 400

    items = data.get('pages')
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'error': 'pages 不能为空'}), 400

    config = load_config()
    results = []
    for item in items:
        if not isinstance(item, dict) or not item.get('pageId'):
            results.append({'pageId': item.get('pageId') if isinstance(item, dict) else None, 'success': False, 'error': '缺少 pageId'})
            continue

        page_id = str(item['pageId'])
        page = None
        for p in config.get('pages', []):
            if str(p.get('id')) == page_id:
                page = p
                break

        if not page:
            results.append({'pageId': page_id, 'success': False, 'error': '页面不存在'})
            continue

        changed = False

        # 1) 页面级展示字段（title / share_title / share_desc / share_icon）
        page_fields = item.get('page')
        if isinstance(page_fields, dict):
            for key in ('title', 'share_title', 'share_desc', 'share_icon'):
                if key in page_fields:
                    page[key] = page_fields[key]
                    changed = True

        # 2) 名片信息区块展示字段（contact）
        contact_fields = item.get('contact')
        if isinstance(contact_fields, dict) and contact_fields:
            contact_section = None
            for sec in page.get('sections', []):
                if sec.get('type') == 'contact':
                    contact_section = sec
                    break
            if not contact_section:
                results.append({'pageId': page_id, 'success': False, 'error': '页面无 contact 名片信息区块'})
                continue
            allowed_contact_keys = ('name', 'title', 'title2', 'phone', 'mobilePhone', 'email',
                                    'company', 'address', 'logo', 'customBgImage')
            for key in allowed_contact_keys:
                if key in contact_fields:
                    contact_section[key] = contact_fields[key]
                    changed = True

        if changed:
            save_config(config)
        results.append({'pageId': page_id, 'success': True, 'changed': changed})

    return jsonify({'success': True, 'results': results})

# ================= 组件映射 / AI 编排 API（纯新增） =================

def _collect_component_list(config, include_detail=False):
    """收集全站组件列表"""
    ensure_section_uids(config)
    items = []
    for page in config.get('pages', []):
        for sec in page.get('sections', []):
            item = {
                'uid': sec.get('uid', ''),
                'type': sec.get('type', ''),
                'pageId': page.get('id', ''),
                'pageTitle': page.get('title', ''),
                'customTitle': sec.get('customTitle', ''),
                'note': sec.get('note', ''),
            }
            if include_detail:
                item['section'] = sec
            items.append(item)
    return items

@app.route('/api/components', methods=['GET'])
def api_components_list():
    """获取所有组件列表（供 AI 编排 / 映射引用）"""
    config = load_config()
    return jsonify({'success': True, 'components': _collect_component_list(config)})

@app.route('/api/components/<uid>', methods=['GET'])
def api_component_get(uid):
    """获取单个组件详情"""
    config = load_config()
    page, section = find_section_by_uid(config, uid)
    if not section:
        return jsonify({'success': False, 'error': '组件不存在'}), 404
    return jsonify({'success': True, 'component': section, 'pageId': page.get('id') if page else None})

@app.route('/api/components/<uid>', methods=['PUT'])
def api_component_update(uid):
    """按 uid 更新组件（供 AI 自动化调整）"""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    config = load_config()
    page, section = find_section_by_uid(config, uid)
    if not section:
        return jsonify({'success': False, 'error': '组件不存在'}), 404
    # 不允许通过该接口修改 uid / type，防止破坏映射关系
    for k, v in data.items():
        if k in ('uid', 'type'):
            continue
        section[k] = v
    save_config(config)
    return jsonify({'success': True, 'component': section})

@app.route('/api/components/<uid>', methods=['DELETE'])
def api_component_delete(uid):
    """删除指定 uid 的组件"""
    config = load_config()
    for page in config.get('pages', []):
        for i, sec in enumerate(page.get('sections', [])):
            if sec.get('uid') == uid:
                del page['sections'][i]
                save_config(config)
                return jsonify({'success': True, 'message': '组件已删除'})
    return jsonify({'success': False, 'error': '组件不存在'}), 404

@app.route('/api/pages/<page_id>/components', methods=['POST'])
def api_component_create(page_id):
    """在指定页面新增组件（供 AI 编排）"""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    config = load_config()
    page = None
    for p in config.get('pages', []):
        if p['id'] == page_id:
            page = p
            break
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404

    section = data.get('section') or data.get('components')
    if not isinstance(section, dict) or 'type' not in section:
        return jsonify({'success': False, 'error': '缺少组件类型'}), 400

    if 'uid' not in section or not section['uid']:
        section['uid'] = 'sec_' + uuid.uuid4().hex[:12]
    index = data.get('index')
    if index is not None and isinstance(index, int) and 0 <= index <= len(page['sections']):
        page['sections'].insert(index, section)
    else:
        page['sections'].append(section)
    save_config(config)
    return jsonify({'success': True, 'component': section})

@app.route('/api/mapping', methods=['POST'])
def api_mapping_create():
    """创建映射组件：直接复制其他组件的唯一ID进行展示，支持多个有序映射"""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    page_id = data.get('pageId')
    ref_uids = data.get('refUids')
    if not isinstance(ref_uids, list) or not ref_uids:
        ref_uids = [data.get('refUid')] if data.get('refUid') else []
    ref_uids = [str(u).strip() for u in ref_uids if u and str(u).strip()]
    if not page_id or not ref_uids:
        return jsonify({'success': False, 'error': '缺少 pageId 或 refUid/refUids'}), 400

    config = load_config()
    page = None
    for p in config.get('pages', []):
        if p['id'] == page_id:
            page = p
            break
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404

    mapped_from = []
    for ref_uid in ref_uids:
        ref_page, ref_section = find_section_by_uid(config, ref_uid)
        if not ref_section:
            return jsonify({'success': False, 'error': f'被引用的组件不存在: {ref_uid}'}), 404
        mapped_from.append(ref_section)

    mapping = {
        'type': 'mapping',
        'refUids': ref_uids,
        'refUid': ref_uids[0],
        'uid': 'sec_' + uuid.uuid4().hex[:12],
        'margin': data.get('margin', 0),
        'borderRadius': data.get('borderRadius', 0),
        'customTitle': data.get('customTitle', '')
    }
    index = data.get('index')
    if index is not None and isinstance(index, int) and 0 <= index <= len(page['sections']):
        page['sections'].insert(index, mapping)
    else:
        page['sections'].append(mapping)
    save_config(config)
    return jsonify({'success': True, 'component': mapping, 'mappedFrom': mapped_from})

@app.route('/api/groups', methods=['GET'])
def get_groups():
    """获取所有分组"""
    config = load_config()
    if 'groups' not in config or not config['groups']:
        config['groups'] = [{
            'id': 'default',
            'name': '默认分组',
            'description': '默认页面分组'
        }]
        save_config(config)
    return jsonify({'groups': config['groups']})

@app.route('/api/share-card-image')
def share_card_image():
    """生成微信分享卡片图片"""
    from share_card import generate_share_card, get_cache_key
    config = load_config()

    page_id = request.args.get('page')
    page = None
    if page_id:
        for p in config.get('pages', []):
            if p['id'] == page_id:
                page = p
                break
    else:
        default_page_id = config.get('settings', {}).get('defaultPage', 'home')
        for p in config.get('pages', []):
            if p['id'] == default_page_id:
                page = p
                break

    contact_section = None
    if page:
        for sec in page.get('sections', []):
            if sec.get('type') == 'contact':
                contact_section = sec
                break

    basic_info = config.get('basicInfo', {})
    info = {**basic_info, **(contact_section or {})}

    cache_key = get_cache_key(info)
    result = generate_share_card(info, cache_key=cache_key)

    if isinstance(result, str):
        return send_file(result, mimetype='image/png')
    else:
        return send_file(result, mimetype='image/png')

@app.route('/share-card')
def share_card_page():
    """分享卡片预览页面"""
    config = load_config()

    page_id = request.args.get('page')
    page = None
    if page_id:
        for p in config.get('pages', []):
            if p['id'] == page_id:
                page = p
                break
    else:
        default_page_id = config.get('settings', {}).get('defaultPage', 'home')
        for p in config.get('pages', []):
            if p['id'] == default_page_id:
                page = p
                break

    contact_section = None
    if page:
        for sec in page.get('sections', []):
            if sec.get('type') == 'contact':
                contact_section = sec
                break

    basic_info = config.get('basicInfo', {})
    info = {**basic_info, **(contact_section or {})}

    from share_card import get_cache_key
    cache_key = get_cache_key(info)
    share_image_url = f"{current_domain}/api/share-card-image"
    if page_id:
        share_image_url += f"?page={page_id}"

    logo_url = info.get('logo', '')
    if logo_url and not logo_url.startswith('http'):
        logo_url = current_domain + '/' + logo_url.lstrip('/')

    return render_template('share-card.html',
        name=info.get('name', ''),
        phone=info.get('phone', ''),
        title=info.get('title', ''),
        title2=info.get('title2', ''),
        email=info.get('email', ''),
        logo_url=logo_url,
        share_image_url=share_image_url
    )


# =========================================================================
# AI 管理与编辑 API（Token 鉴权，供 AI / 外部系统操作页面）
# 统一前缀 /api/v1，鉴权方式：请求头 X-API-Token 或查询参数 ?token=
# =========================================================================

AI_API_TOKEN = 'wswwsw1234'  # 与 seo_helper 的 API_TOKEN 保持一致


def _api_token_ok():
    """校验 AI API 访问 token"""
    token = request.headers.get('X-API-Token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '')
    return token == AI_API_TOKEN


def _require_ai_token(f):
    """AI API token 鉴权装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _api_token_ok():
            return jsonify({'success': False, 'error': 'Unauthorized: 缺少或错误的 API Token'}), 401
        return f(*args, **kwargs)
    return decorated


def _find_page(config, page_id):
    for p in config.get('pages', []):
        if str(p.get('id')) == str(page_id):
            return p
    return None


def _find_page_and_section(config, page_id=None, uid=None):
    """按 uid 定位区块，返回 (page, section)；也可限定在某页面内"""
    for page in config.get('pages', []):
        if page_id and str(page.get('id')) != str(page_id):
            continue
        for section in page.get('sections', []):
            if section.get('uid') == uid:
                return page, section
    return None, None


def _safe_float(v, default=None):
    try:
        if v is None or v == '':
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


def _safe_int(v, default=None):
    try:
        if v is None or v == '':
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


def _sanitize_page_id(page_id):
    """规范化页面 ID：小写、空格转下划线"""
    return str(page_id).strip().lower().replace(' ', '_')


# ---------------- 页面管理 API ----------------

@app.route('/api/v1/pages', methods=['GET'])
@_require_ai_token
def api_v1_pages_list():
    """获取所有页面（列表模式，不含 sections 详情，可用 ?detail=1 展开）"""
    config = load_config()
    detail = request.args.get('detail') in ('1', 'true', 'yes')
    pages = []
    for p in config.get('pages', []):
        item = {
            'id': p.get('id'),
            'title': p.get('title', ''),
            'groupId': p.get('groupId', 'default'),
            'share_title': p.get('share_title', ''),
            'share_desc': p.get('share_desc', ''),
            'share_icon': p.get('share_icon', ''),
            'section_count': len(p.get('sections', [])),
        }
        if detail:
            item['sections'] = p.get('sections', [])
        pages.append(item)
    return jsonify({'success': True, 'count': len(pages), 'pages': pages})


@app.route('/api/v1/pages/<page_id>', methods=['GET'])
@_require_ai_token
def api_v1_page_get(page_id):
    """获取单个页面完整配置"""
    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404
    return jsonify({'success': True, 'page': page})


@app.route('/api/v1/pages', methods=['POST'])
@_require_ai_token
def api_v1_page_create():
    """创建新页面

    请求体: {
      "id": "page_id" (可选，缺省自动生成),
      "title": "页面标题" (必填),
      "groupId": "default" (可选),
      "share_title": "", "share_desc": "", "share_icon": "" (可选),
      "sections": [...] (可选)
    }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    title = str(data.get('title', '')).strip()
    if not title:
        return jsonify({'success': False, 'error': '缺少页面标题 title'}), 400

    config = load_config()
    page_id = _sanitize_page_id(data.get('id') or data.get('pageId') or '')
    if not page_id:
        page_id = 'page_' + uuid.uuid4().hex[:6]
    # 自动加后缀避免冲突
    base_id = page_id
    suffix = 1
    while _find_page(config, page_id):
        page_id = f"{base_id}_{suffix}"
        suffix += 1

    new_page = {
        'id': page_id,
        'title': title,
        'groupId': str(data.get('groupId', 'default')),
        'sections': [],
        'share_title': str(data.get('share_title', '')),
        'share_desc': str(data.get('share_desc', '')),
        'share_icon': str(data.get('share_icon', '')),
        'mobile_gap': _safe_int(data.get('mobile_gap'), 10),
    }
    sections = data.get('sections')
    if isinstance(sections, list):
        for sec in sections:
            if isinstance(sec, dict) and 'type' in sec:
                if 'uid' not in sec or not sec['uid']:
                    sec['uid'] = 'sec_' + uuid.uuid4().hex[:12]
                new_page['sections'].append(sec)
    config.setdefault('pages', []).append(new_page)
    save_config(config)
    return jsonify({'success': True, 'page': new_page}), 201


@app.route('/api/v1/pages/<page_id>', methods=['PUT'])
@_require_ai_token
def api_v1_page_update(page_id):
    """更新页面级字段（title/groupId/share_title/share_desc/share_icon/mobile_gap 等）"""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404

    allowed = ('title', 'groupId', 'share_title', 'share_desc', 'share_icon', 'mobile_gap',
               'page_bg_theme', 'page_custom_bg_image', 'page_bg_scale_mode',
               'card_bg_theme', 'card_custom_bg_image')
    changed = False
    for key in allowed:
        if key in data:
            if key == 'mobile_gap':
                page[key] = _safe_int(data[key], page.get('mobile_gap', 10))
            else:
                page[key] = data[key]
            changed = True
    if changed:
        save_config(config)
    return jsonify({'success': True, 'page': page})


@app.route('/api/v1/pages/<page_id>', methods=['DELETE'])
@_require_ai_token
def api_v1_page_delete(page_id):
    """删除页面"""
    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404
    config['pages'] = [p for p in config['pages'] if str(p.get('id')) != str(page_id)]
    save_config(config)
    return jsonify({'success': True, 'message': f'页面 {page_id} 已删除'})


# ---------------- 区块(组件)管理 API ----------------

@app.route('/api/v1/pages/<page_id>/sections', methods=['GET'])
@_require_ai_token
def api_v1_sections_list(page_id):
    """获取页面内所有区块"""
    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404
    return jsonify({'success': True, 'sections': page.get('sections', [])})


@app.route('/api/v1/pages/<page_id>/sections', methods=['POST'])
@_require_ai_token
def api_v1_section_create(page_id):
    """在页面中新增区块（支持 ?position=top|bottom|INDEX）

    请求体: { "section": { "type": "image", ... }, "position": "bottom" }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    section = data.get('section')
    if not isinstance(section, dict) or not section.get('type'):
        return jsonify({'success': False, 'error': '缺少区块类型 section.type'}), 400

    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404

    if 'uid' not in section or not section['uid']:
        section['uid'] = 'sec_' + uuid.uuid4().hex[:12]

    position = data.get('position', 'bottom')
    sections = page.setdefault('sections', [])
    if position == 'top':
        sections.insert(0, section)
    elif isinstance(position, int) or (isinstance(position, str) and position.lstrip('-').isdigit()):
        idx = int(position)
        idx = max(0, min(idx, len(sections)))
        sections.insert(idx, section)
    else:
        sections.append(section)
    save_config(config)
    return jsonify({'success': True, 'section': section}), 201


@app.route('/api/v1/sections/<uid>', methods=['GET'])
@_require_ai_token
def api_v1_section_get(uid):
    """获取单个区块详情"""
    config = load_config()
    page, section = _find_page_and_section(config, uid=uid)
    if not section:
        return jsonify({'success': False, 'error': '区块不存在'}), 404
    return jsonify({'success': True, 'section': section, 'pageId': page.get('id') if page else None})


@app.route('/api/v1/sections/<uid>', methods=['PUT'])
@_require_ai_token
def api_v1_section_update(uid):
    """更新区块字段（不可改 uid/type）

    请求体: { "title": "新标题", "src": "新图片URL", ... }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    config = load_config()
    page, section = _find_page_and_section(config, uid=uid)
    if not section:
        return jsonify({'success': False, 'error': '区块不存在'}), 404
    for k, v in data.items():
        if k in ('uid', 'type'):
            continue
        section[k] = v
    save_config(config)
    return jsonify({'success': True, 'section': section})


@app.route('/api/v1/sections/<uid>', methods=['DELETE'])
@_require_ai_token
def api_v1_section_delete(uid):
    """删除区块（支持嵌套：顶层区块或 tabs 内嵌区块）"""
    config = load_config()
    for page in config.get('pages', []):
        sections = page.get('sections', [])
        for i, sec in enumerate(sections):
            if sec.get('uid') == uid:
                del sections[i]
                save_config(config)
                return jsonify({'success': True, 'message': '区块已删除'})
            if sec.get('type') == 'tabs':
                for tab in sec.get('tabs', []):
                    t_secs = tab.get('sections', [])
                    for j, t_sec in enumerate(t_secs):
                        if t_sec.get('uid') == uid:
                            del t_secs[j]
                            save_config(config)
                            return jsonify({'success': True, 'message': '区块已删除（tabs内嵌）'})
    return jsonify({'success': False, 'error': '区块不存在'}), 404


@app.route('/api/v1/pages/<page_id>/sections/reorder', methods=['POST'])
@_require_ai_token
def api_v1_sections_reorder(page_id):
    """重排页面区块顺序

    请求体: { "uids": ["sec_xxx", "sec_yyy", ...] }  按该顺序排列全部区块
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or not isinstance(data.get('uids'), list):
        return jsonify({'success': False, 'error': '缺少 uids 数组'}), 400
    uids = [str(u) for u in data['uids']]
    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404
    sections = page.get('sections', [])
    by_uid = {sec.get('uid'): sec for sec in sections}
    if any(u not in by_uid for u in uids):
        return jsonify({'success': False, 'error': 'uids 中存在不存在的区块'}), 400
    if len(uids) != len(sections):
        return jsonify({'success': False, 'error': f'uids 数量({len(uids)})与区块数量({len(sections)})不一致'}), 400
    page['sections'] = [by_uid[u] for u in uids]
    save_config(config)
    return jsonify({'success': True, 'sections': page['sections']})


# ---------------- 批量操作 API ----------------

@app.route('/api/v1/batch/update-pages', methods=['POST'])
@_require_ai_token
def api_v1_batch_update_pages():
    """批量更新多个页面的字段

    请求体: {
      "pages": [ { "pageId": "x", "title": "...", "share_title": "..." }, ... ],
      "onlyChange": true (可选，true 时页面字段需与 pageId 同级传入)
    }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or not isinstance(data.get('pages'), list):
        return jsonify({'success': False, 'error': '缺少 pages 数组'}), 400
    items = data['pages']
    config = load_config()
    results = []
    changed_any = False
    for item in items:
        if not isinstance(item, dict):
            results.append({'success': False, 'error': '无效条目'})
            continue
        pid = item.get('pageId') or item.get('page')
        page = _find_page(config, pid)
        if not page:
            results.append({'pageId': pid, 'success': False, 'error': '页面不存在'})
            continue
        target = item.get('fields') if isinstance(item.get('fields'), dict) else item
        allowed = ('title', 'groupId', 'share_title', 'share_desc', 'share_icon', 'mobile_gap',
                   'page_bg_theme', 'page_custom_bg_image', 'page_bg_scale_mode',
               'card_bg_theme', 'card_custom_bg_image')
        changed = False
        for key in allowed:
            if key in target:
                if key == 'mobile_gap':
                    page[key] = _safe_int(target[key], page.get('mobile_gap', 10))
                else:
                    page[key] = target[key]
                changed = True
        if changed:
            changed_any = True
        results.append({'pageId': pid, 'success': True, 'changed': changed})
    if changed_any:
        save_config(config)
    return jsonify({'success': True, 'results': results})


@app.route('/api/v1/batch/sections', methods=['POST'])
@_require_ai_token
def api_v1_batch_sections():
    """批量创建/更新/删除区块

    请求体: {
      "pageId": "x",
      "create": [ {section...} ],                       // 新建（追加到末尾）
      "update": [ { "uid": "sec_x", ...字段 } ],        // 更新
      "delete": [ "sec_x", "sec_y" ],                   // 删除
      "reorder": [ "sec_x", "sec_y", ... ]              // 可选，重排
    }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    page_id = data.get('pageId')
    if not page_id:
        return jsonify({'success': False, 'error': '缺少 pageId'}), 400
    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404
    sections = page.setdefault('sections', [])
    created, updated, deleted = [], [], []

    for sec in data.get('create', []) or []:
        if isinstance(sec, dict) and sec.get('type'):
            if 'uid' not in sec or not sec['uid']:
                sec['uid'] = 'sec_' + uuid.uuid4().hex[:12]
            sections.append(sec)
            created.append(sec['uid'])

    for upd in data.get('update', []) or []:
        if not isinstance(upd, dict) or not upd.get('uid'):
            continue
        for sec in sections:
            if sec.get('uid') == upd['uid']:
                for k, v in upd.items():
                    if k in ('uid', 'type'):
                        continue
                    sec[k] = v
                updated.append(upd['uid'])
                break

    for uid in data.get('delete', []) or []:
        before = len(sections)
        sections[:] = [s for s in sections if s.get('uid') != uid]
        if len(sections) < before:
            deleted.append(uid)

    reorder = data.get('reorder')
    if isinstance(reorder, list) and reorder:
        by_uid = {sec.get('uid'): sec for sec in sections}
        if all(u in by_uid for u in reorder) and len(reorder) == len(sections):
            sections[:] = [by_uid[u] for u in reorder]

    save_config(config)
    return jsonify({'success': True, 'created': created, 'updated': updated, 'deleted': deleted,
                    'section_count': len(sections)})


@app.route('/api/v1/batch/delete-pages', methods=['POST'])
@_require_ai_token
def api_v1_batch_delete_pages():
    """批量删除页面

    请求体: { "pageIds": ["a", "b", "c"] }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or not isinstance(data.get('pageIds'), list):
        return jsonify({'success': False, 'error': '缺少 pageIds 数组'}), 400
    ids = [str(i) for i in data['pageIds']]
    config = load_config()
    remaining = []
    deleted = []
    not_found = []
    for p in config.get('pages', []):
        if str(p.get('id')) in ids:
            deleted.append(p.get('id'))
        else:
            remaining.append(p)
    for i in ids:
        if i not in deleted:
            not_found.append(i)
    config['pages'] = remaining
    if deleted:
        save_config(config)
    return jsonify({'success': True, 'deleted': deleted, 'notFound': not_found})


# ---------------- 分组管理 API ----------------

@app.route('/api/v1/groups', methods=['GET'])
@_require_ai_token
def api_v1_groups_list():
    """获取所有分组及其页面数量"""
    config = load_config()
    groups = config.get('groups', []) or []
    page_count = {}
    for p in config.get('pages', []):
        gid = p.get('groupId', 'default')
        page_count[gid] = page_count.get(gid, 0) + 1
    result = []
    for g in groups:
        item = dict(g)
        item['pageCount'] = page_count.get(g.get('id'), 0)
        result.append(item)
    return jsonify({'success': True, 'groups': result})


@app.route('/api/v1/groups', methods=['POST'])
@_require_ai_token
def api_v1_group_create():
    """创建分组

    请求体: { "id": "xxx"(可选), "name": "分组名"(必填), "description": ""(可选) }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    name = str(data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': '缺少分组名称 name'}), 400
    config = load_config()
    groups = config.setdefault('groups', [])
    gid = _sanitize_page_id(data.get('id') or '')
    if not gid:
        gid = 'group_' + uuid.uuid4().hex[:6]
    if any(g.get('id') == gid for g in groups):
        return jsonify({'success': False, 'error': f'分组ID已存在: {gid}'}), 400
    new_group = {'id': gid, 'name': name, 'description': str(data.get('description', ''))}
    groups.append(new_group)
    save_config(config)
    return jsonify({'success': True, 'group': new_group}), 201


@app.route('/api/v1/groups/<group_id>', methods=['PUT'])
@_require_ai_token
def api_v1_group_update(group_id):
    """更新分组（name / description）"""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'success': False, 'error': '无效的数据'}), 400
    config = load_config()
    group = None
    for g in config.get('groups', []):
        if g.get('id') == group_id:
            group = g
            break
    if not group:
        return jsonify({'success': False, 'error': '分组不存在'}), 404
    if 'name' in data:
        group['name'] = str(data['name'])
    if 'description' in data:
        group['description'] = str(data['description'])
    save_config(config)
    return jsonify({'success': True, 'group': group})


@app.route('/api/v1/groups/<group_id>', methods=['DELETE'])
@_require_ai_token
def api_v1_group_delete(group_id):
    """删除分组（组内页面移回默认分组）"""
    config = load_config()
    groups = config.get('groups', [])
    if not any(g.get('id') == group_id for g in groups):
        return jsonify({'success': False, 'error': '分组不存在'}), 404
    config['groups'] = [g for g in groups if g.get('id') != group_id]
    for p in config.get('pages', []):
        if p.get('groupId') == group_id:
            p['groupId'] = 'default'
    save_config(config)
    return jsonify({'success': True, 'message': f'分组 {group_id} 已删除，组内页面已移回默认分组'})


@app.route('/api/v1/pages/<page_id>/move', methods=['POST'])
@_require_ai_token
def api_v1_page_move(page_id):
    """移动页面到指定分组

    请求体: { "groupId": "target" }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or not data.get('groupId'):
        return jsonify({'success': False, 'error': '缺少 groupId'}), 400
    config = load_config()
    page = _find_page(config, page_id)
    if not page:
        return jsonify({'success': False, 'error': '页面不存在'}), 404
    target = str(data['groupId'])
    if not any(g.get('id') == target for g in config.get('groups', [])):
        return jsonify({'success': False, 'error': f'分组不存在: {target}'}), 404
    page['groupId'] = target
    save_config(config)
    return jsonify({'success': True, 'pageId': page_id, 'groupId': target})


# ---------------- 配置读取 / 搜索 API ----------------

@app.route('/api/v1/config', methods=['GET'])
@_require_ai_token
def api_v1_config():
    """获取全量配置（basicInfo / settings / pages 完整内容）"""
    config = load_config()
    return jsonify({'success': True, 'config': config})


@app.route('/api/v1/config/basic', methods=['GET'])
@_require_ai_token
def api_v1_config_basic():
    """获取 basicInfo 与 settings"""
    config = load_config()
    return jsonify({'success': True, 'basicInfo': config.get('basicInfo', {}),
                    'settings': config.get('settings', {})})


@app.route('/api/v1/search', methods=['GET'])
@_require_ai_token
def api_v1_search():
    """按关键词搜索页面/区块

    用法: /api/v1/search?q=关键词&scope=page|section|all
    """
    q = (request.args.get('q') or '').strip()
    scope = request.args.get('scope', 'all')
    if not q:
        return jsonify({'success': False, 'error': '缺少搜索关键词 q'}), 400
    config = load_config()
    pages_result, sections_result = [], []
    for page in config.get('pages', []):
        if scope in ('all', 'page'):
            hay = json.dumps({k: v for k, v in page.items() if k != 'sections'}, ensure_ascii=False)
            if q.lower() in hay.lower():
                pages_result.append({'id': page.get('id'), 'title': page.get('title')})
        if scope in ('all', 'section'):
            for sec in page.get('sections', []):
                hay = json.dumps(sec, ensure_ascii=False)
                if q.lower() in hay.lower():
                    sections_result.append({'uid': sec.get('uid'), 'type': sec.get('type'),
                                            'pageId': page.get('id'), 'pageTitle': page.get('title')})
    return jsonify({'success': True, 'pages': pages_result, 'sections': sections_result})


@app.route('/api/v1/ping', methods=['GET'])
def api_v1_ping():
    """健康检查（无需鉴权）"""
    return jsonify({'success': True, 'service': 'WeChat-Card', 'version': '1.0',
                    'api': 'v1', 'time': int(time.time())})


def get_local_ip():
    """自动获取本地IP地址"""
    try:
        # 创建一个UDP套接字
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 连接到一个外部服务器，不需要实际发送数据
        s.connect(('8.8.8.8', 80))
        # 获取本地IP地址
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        # 如果获取失败，返回默认IP
        return '127.0.0.1'



# 全局变量：当前使用的域名
local_ip = get_local_ip()
current_domain = 'http://szdptk.com:8000'  # 默认使用外网模式

def get_current_domain():
    """获取当前使用的域名"""
    return current_domain

if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='微信名片H5签名服务')
    parser.add_argument('--mode', choices=['internal', 'external'], default='external',
                      help='选择运行模式: internal (内网模式, 使用自动获取的IP), external (外网模式, http://szdptk.com:8000)')
    args = parser.parse_args()
    
    # 更新全局变量
    if args.mode == 'external':
        current_domain = 'http://szdptk.com:8000'
    else:
        current_domain = f'http://{local_ip}:8000'
    
    print("微信名片H5签名服务启动中...")
    print(f"当前模式: {'外网模式' if args.mode == 'external' else '内网模式'}")
    print(f"当前域名: {current_domain}")
    print(f"服务地址: http://0.0.0.0:8000")
    print(f"API接口:")
    print(f"  GET /api/wechat-sign?url=YOUR_URL - 获取微信签名")
    print(f"  GET /api/card-config?page=PAGE_ID - 获取名片配置")
    print(f"后台管理:")
    print(f"  http://0.0.0.0:8000/admin - 管理界面 (用户名: admin, 密码: admin123)")

    print("\n注意: 请确保上传目录存在且可写")
    # 在8000端口启动HTTP
    app.run(host='0.0.0.0', port=8000, debug=False)
