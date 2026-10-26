#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信名片H5签名服务 - Flask版本
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
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash, send_from_directory

# 微信配置
APP_ID = 'wx3af2c6733acfc3e2'
APP_SECRET = '6919e48b7044b36eda39ac4ce797f8a3'

# 缓存
access_token = None
token_expire = 0
jsapi_ticket = None
ticket_expire = 0

# 上传配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}

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
    'pages': [
        {
            'id': 'home',
            'title': '首页',
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
            token_expire = time.time() + (data['expires_in'] - 300)
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
            ticket_expire = time.time() + (data['expires_in'] - 300)
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
    
    string1 = f"jsapi_ticket={ticket}&noncestr={nonce_str}&timestamp={timestamp}&url={url}"
    signature = hashlib.sha1(string1.encode('utf-8')).hexdigest()
    
    return {
        'appId': APP_ID,
        'timestamp': timestamp,
        'nonceStr': nonce_str,
        'signature': signature
    }

def get_local_ip():
    """获取本地IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

# 解析命令行参数
parser = argparse.ArgumentParser(description='微信名片H5签名服务')
parser.add_argument('--mode', choices=['internal', 'external'], default='external',
                  help='选择运行模式')
args = parser.parse_args()

local_ip = get_local_ip()
current_domain = 'http://119.145.17.34:8000' if args.mode == 'external' else f'http://{local_ip}:8000'

# 创建Flask应用
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=PROJECT_DIR,
            static_url_path='')

app.secret_key = 'wechat-card-secret-key-2024'

# 添加自定义过滤器
@app.template_filter('enumerate')
def jinja2_enumerate(seq):
    return list(enumerate(seq))

def get_page_by_id(config, page_id):
    """根据page_id获取页面对象，如果不存在则返回None"""
    for page in config.get('pages', []):
        if page['id'] == page_id:
            return page
    return None

def set_default_page_logic(config):
    """设置默认页面逻辑"""
    pages = config.get('pages', [])
    if not pages:
        return config
    
    settings = config.get('settings', {})
    default_page_id = settings.get('defaultPage')
    
    # 优先使用设置的默认页面
    if default_page_id:
        page = get_page_by_id(config, default_page_id)
        if page:
            config['currentPage'] = page
            return config
    
    # 如果默认页面不存在，使用第一个页面
    config['currentPage'] = pages[0]
    return config

# 首页
@app.route('/')
def root():
    config = load_config()
    page_id = request.args.get('page')
    if page_id:
        page = get_page_by_id(config, page_id)
        if page:
            config['currentPage'] = page
    else:
        config = set_default_page_logic(config)
    
    # 更新分享信息
    current_page = config.get('currentPage', {})
    return render_template(
        "index-dynamic.html",
        share_title=current_page.get('share_title') or config.get('basicInfo', {}).get('name', '微信名片'),
        share_desc=current_page.get('share_desc') or config.get('basicInfo', {}).get('title', ''),
        share_icon=current_page.get('share_icon') or config.get('basicInfo', {}).get('logo', ''),
        current_domain=current_domain,
        now_ts=int(time.time()),
    )

# 动态页面
@app.route('/index-dynamic.html')
def index_dynamic():
    config = load_config()
    page_id = request.args.get('page')
    
    if page_id:
        page = get_page_by_id(config, page_id)
        if page:
            config['currentPage'] = page
    else:
        config = set_default_page_logic(config)
    
    current_page = config.get('currentPage', {})
    return render_template(
        "index-dynamic.html",
        share_title=current_page.get('share_title') or config.get('basicInfo', {}).get('name', '微信名片'),
        share_desc=current_page.get('share_desc') or config.get('basicInfo', {}).get('title', ''),
        share_icon=current_page.get('share_icon') or config.get('basicInfo', {}).get('logo', ''),
        current_domain=current_domain,
        now_ts=int(time.time()),
    )

# API: 获取微信签名
@app.route('/api/wechat-sign')
def wechat_sign():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': '缺少url参数'}), 400
    
    sign_data = generate_signature(url)
    if sign_data:
        return jsonify(sign_data)
    else:
        return jsonify({'error': '生成签名失败'}), 500

# API: 获取名片配置
@app.route('/api/card-config')
def card_config():
    config = load_config()
    
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    page_id = request.args.get('page')
    if page_id:
        page = get_page_by_id(config, page_id)
        if page:
            config['currentPage'] = page
    else:
        config = set_default_page_logic(config)
    
    return jsonify(config)

# 后台管理首页
@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    return render_template("admin.html")

# 登录页面
@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            return redirect(url_for('admin'), code=303)
        else:
            return render_template("login.html", error="用户名或密码错误")
    
    return render_template("login.html", error=None)

# 登出
@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# 页面管理
@app.route('/admin/pages')
def pages():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    config = load_config()
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    return render_template("pages.html", pages=config.get('pages', []), current_domain=current_domain)

# 创建页面
@app.route('/admin/pages/create', methods=['GET', 'POST'])
def create_page():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        page_id = request.form.get('page_id')
        page_title = request.form.get('page_title')
        
        if not page_id or not page_title:
            return "页面ID和标题不能为空", 400
        
        config = load_config()
        for p in config.get('pages', []):
            if p['id'] == page_id:
                return "页面ID已存在", 400
        
        new_page = {
            'id': page_id,
            'title': page_title,
            'sections': []
        }
        
        if 'pages' not in config:
            config['pages'] = []
        
        config['pages'].append(new_page)
        save_config(config)
        
        return redirect(url_for('pages'))
    
    return render_template("create_page.html")

# 编辑页面
@app.route('/admin/pages/edit/<page_id>', methods=['GET', 'POST'])
def edit_page(page_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    config = load_config()
    
    page = None
    for p in config.get('pages', []):
        if p['id'] == page_id:
            page = p
            break
    
    if not page:
        return "页面不存在", 404
    
    if request.method == 'POST':
        page_title = request.form.get('page_title')
        if page_title:
            page['title'] = page_title
            save_config(config)
        return redirect(url_for('edit_page', page_id=page_id))
    
    return render_template("edit_sections.html", page_id=page_id, page_title=page.get('title', ''), page=page, sections=page.get('sections', []))

# 编辑页面内容区块
@app.route('/admin/pages/sections/<page_id>', methods=['GET', 'POST'])
def edit_page_sections(page_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    config = load_config()
    
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    
    page = None
    for p in config['pages']:
        if p['id'] == page_id:
            page = p
            break
    
    if not page:
        return "页面不存在", 404
    
    if request.method == 'GET':
        return render_template("edit_sections.html", page_id=page_id, page_title=page.get('title', ''), page=page, sections=page.get('sections', []))
    
    form_data = request.form
    
    # 保存分享设置
    page['share_title'] = form_data.get('share_title', '')
    page['share_desc'] = form_data.get('share_desc', '')
    page['share_icon'] = form_data.get('share_icon', '')
    
    # 保存分割线设置
    page['divider_height'] = form_data.get('divider_height', 1)
    page['divider_spacing'] = form_data.get('divider_spacing', 20)
    page['divider_color'] = form_data.get('divider_color', '#e0e0e0')
    
    # 转换为正确的类型
    try:
        page['divider_height'] = int(page['divider_height'])
    except:
        page['divider_height'] = 1
    try:
        page['divider_spacing'] = int(page['divider_spacing'])
    except:
        page['divider_spacing'] = 20
    
    # 处理区块编辑
    sections = []
    section_count = int(form_data.get('section_count', '0'))
    
    for i in range(section_count):
        section_type = form_data.get(f'section_type_{i}')
        
        if not section_type:
            if form_data.get(f'section_src_{i}'):
                if form_data.get(f'section_poster_{i}'):
                    section_type = 'video'
                else:
                    section_type = 'image'
            elif form_data.get(f'section_title_{i}'):
                section_type = 'title'
            elif form_data.get(f'image_count_{i}'):
                section_type = 'grid'
            elif form_data.get(f'carousel_item_count_{i}'):
                section_type = 'carousel'
            elif form_data.get(f'tabs_count_{i}'):
                section_type = 'tabs'
            else:
                continue
        
        if section_type == 'title':
            section = {
                'type': 'title',
                'level': int(form_data.get(f'section_level_{i}', '1')),
                'title': form_data.get(f'section_title_{i}', ''),
                'color': form_data.get(f'section_color_{i}', ''),
                'logo': form_data.get(f'section_logo_{i}', '')
            }
        elif section_type == 'image':
            section = {
                'type': 'image',
                'src': form_data.get(f'section_src_{i}', ''),
                'jump': form_data.get(f'section_jump_{i}', '')
            }
        elif section_type == 'video':
            section = {
                'type': 'video',
                'src': form_data.get(f'section_src_{i}', ''),
                'poster': form_data.get(f'section_poster_{i}', '')
            }
        elif section_type == 'grid':
            images = []
            image_count = int(form_data.get(f'image_count_{i}', '0'))
            for j in range(image_count):
                image = {
                    'src': form_data.get(f'image_src_{i}_{j}', ''),
                    'jump': form_data.get(f'image_jump_{i}_{j}', '')
                }
                images.append(image)
            section = {
                'type': 'grid',
                'images': images
            }
        elif section_type == 'contact':
            section = {
                'type': 'contact',
                'bgTheme': form_data.get(f'contact_bgTheme_{i}', 'theme-purple-pink'),
                'contentTheme': form_data.get(f'contact_contentTheme_{i}', 'theme-purple-pink'),
                'name': form_data.get(f'contact_name_{i}', ''),
                'title': form_data.get(f'contact_title_{i}', ''),
                'title2': form_data.get(f'contact_title2_{i}', ''),
                'phone': form_data.get(f'contact_phone_{i}', ''),
                'email': form_data.get(f'contact_email_{i}', ''),
                'logo': form_data.get(f'contact_logo_{i}', ''),
                'company': form_data.get(f'contact_company_{i}', ''),
                'address': form_data.get(f'contact_address_{i}', '')
            }
        elif section_type == 'notice':
            section = {
                'type': 'notice',
                'title': form_data.get(f'notice_title_{i}', ''),
                'content': form_data.get(f'notice_content_{i}', ''),
                'tag': form_data.get(f'notice_tag_{i}', ''),
                'autoPopup': 'notice_autoPopup_{i}' in form_data
            }
        elif section_type == 'carousel':
            items = []
            item_count = int(form_data.get(f'carousel_item_count_{i}', '0'))
            for j in range(item_count):
                item = {
                    'src': form_data.get(f'carousel_item_src_{i}_{j}', ''),
                    'jump': form_data.get(f'carousel_item_jump_{i}_{j}', ''),
                    'title': form_data.get(f'carousel_item_title_{i}_{j}', '')
                }
                items.append(item)
            section = {
                'type': 'carousel',
                'items': items,
                'autoplay': f'carousel_autoplay_{i}' in form_data,
                'interval': int(form_data.get(f'carousel_interval_{i}', '3000'))
            }
        elif section_type == 'tabs':
            tabs = []
            tab_count = int(form_data.get(f'tabs_count_{i}', '0'))
            for j in range(tab_count):
                tab_sections = []
                tab_section_count = int(form_data.get(f'tab_{j}_section_count_{i}', '0'))
                for k in range(tab_section_count):
                    tab_section_type = form_data.get(f'tab_{j}_section_type_{i}_{k}')
                    if not tab_section_type:
                        continue
                    
                    if tab_section_type == 'title':
                        tab_section = {
                            'type': 'title',
                            'level': int(form_data.get(f'tab_{j}_section_level_{i}_{k}', '1')),
                            'title': form_data.get(f'tab_{j}_section_title_{i}_{k}', ''),
                            'color': form_data.get(f'tab_{j}_section_color_{i}_{k}', ''),
                            'logo': form_data.get(f'tab_{j}_section_logo_{i}_{k}', '')
                        }
                    elif tab_section_type == 'image':
                        tab_section = {
                            'type': 'image',
                            'src': form_data.get(f'tab_{j}_section_src_{i}_{k}', ''),
                            'jump': form_data.get(f'tab_{j}_section_jump_{i}_{k}', '')
                        }
                    elif tab_section_type == 'video':
                        tab_section = {
                            'type': 'video',
                            'src': form_data.get(f'tab_{j}_section_src_{i}_{k}', ''),
                            'poster': form_data.get(f'tab_{j}_section_poster_{i}_{k}', '')
                        }
                    elif tab_section_type == 'grid':
                        tab_images = []
                        tab_image_count = int(form_data.get(f'tab_{j}_image_count_{i}_{k}', '0'))
                        for l in range(tab_image_count):
                            tab_image = {
                                'src': form_data.get(f'tab_{j}_image_src_{i}_{k}_{l}', ''),
                                'jump': form_data.get(f'tab_{j}_image_jump_{i}_{k}_{l}', '')
                            }
                            tab_images.append(tab_image)
                        tab_section = {
                            'type': 'grid',
                            'images': tab_images
                        }
                    else:
                        continue
                    
                    tab_sections.append(tab_section)
                
                tab = {
                    'title': form_data.get(f'tab_title_{i}_{j}', ''),
                    'sections': tab_sections
                }
                tabs.append(tab)
            section = {
                'type': 'tabs',
                'tabs': tabs
            }
        else:
            continue
        
        sections.append(section)
    
    page['sections'] = sections
    save_config(config)
    
    flash('保存成功！')
    return redirect(url_for('edit_page', page_id=page_id))

# 上传资源
@app.route('/admin/upload', methods=['GET', 'POST'])
def upload():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template("upload.html", file_url=None, error="没有选择文件")
        
        file = request.files['file']
        if not file.filename:
            return render_template("upload.html", file_url=None, error="没有选择文件")
        
        if file and allowed_file(file.filename):
            try:
                ext = os.path.splitext(file.filename)[1].lower()
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                random_str = str(uuid.uuid4().hex)[:8]
                filename = f"{timestamp}_{random_str}{ext}"
                
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                
                file_url = f"{current_domain}/uploads/{filename}"
                
                return render_template("upload.html", file_url=file_url)
            except Exception as e:
                print(f"File upload error: {e}")
                return f"文件上传失败：{str(e)}", 500
        else:
            return "不支持的文件类型", 400
    
    return render_template("upload.html", file_url=None)

# 资源管理
@app.route('/admin/resources')
def resources():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    resources_list = []
    
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                size = stat.st_size
                upload_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                
                ext = os.path.splitext(filename)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif']:
                    file_type = 'image'
                elif ext in ['.mp4']:
                    file_type = 'video'
                else:
                    file_type = 'other'
                
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
    
    return render_template("resources.html", resources=resources_list)

# 删除资源
@app.route('/admin/delete-resource')
def delete_resource():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    filename = request.args.get('filename')
    if filename:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    
    return redirect(url_for('resources_page'))

# 删除页面
@app.route('/admin/pages/delete/<page_id>', methods=['POST'])
def delete_page(page_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    config = load_config()
    config['pages'] = [p for p in config.get('pages', []) if p['id'] != page_id]
    save_config(config)
    
    return redirect(url_for('pages'))

# 设为默认页面
@app.route('/admin/pages/set-default/<page_id>', methods=['POST'])
def set_default_page(page_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    config = load_config()
    config['settings'] = config.get('settings', {})
    config['settings']['defaultPage'] = page_id
    save_config(config)
    
    return redirect(url_for('pages'))

# 获取当前域名
@app.route('/api/current-domain')
def get_current_domain():
    return jsonify({'domain': current_domain})

# 静态文件路由
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    print("微信名片H5签名服务启动中...")
    print(f"当前模式: {'外网模式' if args.mode == 'external' else '内网模式'}")
    print(f"当前域名: {current_domain}")
    print(f"服务地址: http://0.0.0.0:8000")
    print("启动完成！")
    app.run(host='0.0.0.0', port=8000, debug=True)
