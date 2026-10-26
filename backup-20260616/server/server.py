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
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='../', static_url_path='/')
app.secret_key = 'wechat_card_secret_key'
app.config['APPLICATION_ROOT'] = ''
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
CORS(app)  # 允许跨域请求

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
                return json.load(f)
        except:
            return default_config
    return default_config

# 保存配置
def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# 检查文件类型
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

# 名片信息设置
@app.route('/admin/basic-info', methods=['GET', 'POST'])
@login_required
def edit_basic_info():
    config = load_config()
    basic_info = config.get('basicInfo', {})
    
    if request.method == 'POST':
        basic_info['name'] = request.form.get('name', '')
        basic_info['title'] = request.form.get('title', '')
        basic_info['title2'] = request.form.get('title2', '')
        basic_info['phone'] = request.form.get('phone', '')
        basic_info['email'] = request.form.get('email', '')
        basic_info['company'] = request.form.get('company', '')
        basic_info['address'] = request.form.get('address', '')
        basic_info['logo'] = request.form.get('logo', '')
        basic_info['alignment'] = request.form.get('alignment', 'center')
        basic_info['bgTheme'] = request.form.get('bgTheme', 'theme-purple-pink')
        basic_info['useCustomBg'] = request.form.get('useCustomBg') == 'on'
        basic_info['customBgImage'] = request.form.get('customBgImage', '')
        basic_info['noBorder'] = request.form.get('noBorder') == 'on'
        
        try:
            basic_info['logoSize'] = int(request.form.get('logoSize', 150))
        except (ValueError, TypeError):
            basic_info['logoSize'] = 150
        
        try:
            basic_info['borderRadius'] = int(request.form.get('borderRadius', 12))
        except (ValueError, TypeError):
            basic_info['borderRadius'] = 12
        
        config['basicInfo'] = basic_info
        save_config(config)
        flash('名片信息保存成功')
        return redirect(url_for('edit_basic_info'))
    
    return render_template('edit_basic_info.html', basicInfo=basic_info)



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
        page_id = request.form.get('page_id', '').lower().replace(' ', '_')
        page_title = request.form.get('page_title', '')
        
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
        
        save_config(config)
        flash('页面信息更新成功')
        return redirect(url_for('pages'))
    
    return render_template('edit_page.html', page=page, groups=config['groups'])

# 删除页面
@app.route('/admin/pages/delete/<page_id>', methods=['POST'])
def delete_page(page_id):
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    pages = config['pages']
    new_pages = [page for page in pages if page['id'] != page_id]
    
    if len(new_pages) != len(pages):
        config['pages'] = new_pages
        # 如果删除的是默认页面，设置第一个页面为默认
        if config.get('settings', {}).get('defaultPage') == page_id and new_pages:
            config['settings']['defaultPage'] = new_pages[0]['id']
        save_config(config)
        flash('页面删除成功')
    else:
        flash('页面不存在')
    
    return redirect(url_for('pages'))

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
    return render_template('groups.html', groups=config['groups'], pages=config.get('pages', []))

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
                            'decorationColor': request.form.get(f'section_decorationColor_{i}', ''),
                            'color': request.form.get(f'section_color_{i}', ''),
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
                            section['margin'] = int(request.form.get(f'title_margin_{i}') or 10)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['topSpacing'] = int(request.form.get(f'title_top_spacing_{i}') or 40)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['bottomSpacing'] = int(request.form.get(f'title_bottom_spacing_{i}') or 10)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['height'] = int(request.form.get(f'title_height_{i}') or 0)
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
                                else:
                                    continue
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
                            'bgTheme': request.form.get(f'contact_bgTheme_{i}', 'theme-white'),
                            'customBgImage': request.form.get(f'contact_customBgImage_{i}', ''),
                            'contentTheme': request.form.get(f'contact_contentTheme_{i}', 'theme-purple-pink'),
                            'name': request.form.get(f'contact_name_{i}', ''),
                            'title': request.form.get(f'contact_title_{i}', ''),
                            'title2': request.form.get(f'contact_title2_{i}', ''),
                            'phone': request.form.get(f'contact_phone_{i}', ''),
                            'email': request.form.get(f'contact_email_{i}', ''),
                            'logo': request.form.get(f'contact_logo_{i}', ''),
                            'company': request.form.get(f'contact_company_{i}', ''),
                            'address': request.form.get(f'contact_address_{i}', ''),
                            'alignment': request.form.get(f'contact_alignment_{i}', 'center'),
                            'logoSize': 30,
                            'margin': 0,
                            'borderRadius': 12,
                            'noBorder': False
                        }
                        try:
                            section['logoSize'] = int(request.form.get(f'contact_logoSize_{i}') or 30)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['margin'] = int(request.form.get(f'contact_spacing_{i}') or 0)
                        except (ValueError, TypeError):
                            pass
                        try:
                            section['borderRadius'] = int(request.form.get(f'contact_borderRadius_{i}') or 12)
                        except (ValueError, TypeError):
                            pass
                        section['noBorder'] = request.form.get(f'contact_noBorder_{i}') == 'on'
                        section['btn1Jump'] = request.form.get(f'contact_btn1Jump_{i}', '')
                        section['btn1Text'] = request.form.get(f'contact_btn1Text_{i}', '')
                        section['btnColor'] = request.form.get(f'contact_btnColor_{i}', '')
                        section['btnTextColor'] = request.form.get(f'contact_btnTextColor_{i}', '')
                        try:
                            section['btnOpacity'] = float(request.form.get(f'contact_btnOpacity_{i}') or 1.0)
                        except (ValueError, TypeError):
                            section['btnOpacity'] = 1.0
                        try:
                            section['btnFontSize'] = int(request.form.get(f'contact_btnFontSize_{i}') or 24)
                        except (ValueError, TypeError):
                            section['btnFontSize'] = 24
                        try:
                            section['btnScale'] = float(request.form.get(f'contact_btnScale_{i}') or 1.0)
                        except (ValueError, TypeError):
                            section['btnScale'] = 1.0
                        try:
                            section['btnPadding'] = int(request.form.get(f'contact_btnPadding_{i}') or 8)
                        except (ValueError, TypeError):
                            section['btnPadding'] = 8
                        section['btnFontWeight'] = request.form.get(f'contact_btnFontWeight_{i}', '700')
                        try:
                            section['topPadding'] = int(request.form.get(f'contact_topPadding_{i}') or 45)
                        except (ValueError, TypeError):
                            section['topPadding'] = 45
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
                    else:
                        print(f"跳过区块 {i}: 未知类型 {section_type}")
                        continue
                    
                    sections.append(section)
                    print(f"添加区块: {section}")
                except Exception as e:
                    print(f"处理区块 {i} 时出错: {e}")
                    # 单个区块出错不影响其他区块继续处理
                    continue
            
            print(f"最终区块列表: {sections}")
            page['sections'] = sections
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
    return render_template('edit_sections.html', page=page, page_id=page_id, sections=sections)

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
                    results.append({
                        'originalName': original_filename,
                        'url': file_url
                    })
                except Exception as e:
                    print(f"File upload error: {e}")
                    import traceback
                    traceback.print_exc()
        
        if results:
            print(f"Upload successful, {len(results)} files uploaded")
            return jsonify({'success': True, 'paths': results})
        else:
            print("ERROR: No files were successfully uploaded")
            return jsonify({'success': False, 'message': '文件上传失败'})
    return render_template('upload.html')

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
    
    if page_id:
        # 返回指定页面的配置
        for page in config['pages']:
            if page['id'] == page_id:
                config['currentPage'] = page
                break
    else:
        # 返回默认页面
        default_page_id = config.get('settings', {}).get('defaultPage', 'home')
        for page in config['pages']:
            if page['id'] == default_page_id:
                config['currentPage'] = page
                break
    
    # 添加当前域名信息
    config['currentDomain'] = current_domain
    return jsonify(config)

@app.route('/api/update-page', methods=['POST'])
def update_page():
    """更新页面信息"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效的数据'}), 400
    
    page_id = data.get('pageId')
    if not page_id:
        return jsonify({'error': '缺少页面ID'}), 400
    
    config = load_config()
    
    # 查找页面
    page = None
    for p in config['pages']:
        if p['id'] == page_id:
            page = p
            break
    
    if not page:
        return jsonify({'error': '页面不存在'}), 404
    
    # 更新允许的字段
    if 'title' in data:
        page['title'] = data['title']
    if 'groupId' in data:
        page['groupId'] = data['groupId']
    if 'share_title' in data:
        page['share_title'] = data['share_title']
    if 'share_desc' in data:
        page['share_desc'] = data['share_desc']
    if 'share_icon' in data:
        page['share_icon'] = data['share_icon']
    
    save_config(config)
    return jsonify({'success': True, 'message': '页面更新成功'})

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
current_domain = 'http://119.145.17.34:8000'  # 默认使用外网模式

def get_current_domain():
    """获取当前使用的域名"""
    return current_domain

if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='微信名片H5签名服务')
    parser.add_argument('--mode', choices=['internal', 'external'], default='external',
                      help='选择运行模式: internal (内网模式, 使用自动获取的IP), external (外网模式, http://119.145.17.34:8000)')
    args = parser.parse_args()
    
    # 更新全局变量
    if args.mode == 'external':
        current_domain = 'http://119.145.17.34:8000'
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
