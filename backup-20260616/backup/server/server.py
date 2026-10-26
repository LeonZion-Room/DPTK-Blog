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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}
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



# 页面管理
@app.route('/admin/pages')
@login_required
def pages():
    config = load_config()
    # 确保pages键存在
    if 'pages' not in config:
        config['pages'] = []
        save_config(config)
    return render_template('pages.html', pages=config['pages'], current_domain=current_domain)

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
            'sections': []
        }
        
        # 确保pages键存在
        if 'pages' not in config:
            config['pages'] = []
        
        config['pages'].append(new_page)
        save_config(config)
        flash('页面创建成功')
        return redirect(url_for('pages'))
    return render_template('create_page.html')

# 编辑页面
@app.route('/admin/pages/edit/<page_id>', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
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
        page['title'] = request.form.get('page_title', page['title'])
        save_config(config)
        flash('页面信息更新成功')
        return redirect(url_for('pages'))
    
    return render_template('edit_page.html', page=page)

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
        # 保存分享设置
        page['share_title'] = request.form.get('share_title', '')
        page['share_desc'] = request.form.get('share_desc', '')
        page['share_icon'] = request.form.get('share_icon', '')
        
        # 处理区块编辑
        sections = []
        section_count = int(request.form.get('section_count', '0'))
        
        # 打印表单数据，用于调试
        print(f"表单数据: {dict(request.form)}")
        print(f"区块数量: {section_count}")
        
        for i in range(section_count):
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
                    'level': int(request.form.get(f'section_level_{i}', '1')),
                    'title': request.form.get(f'section_title_{i}', ''),
                    'color': request.form.get(f'section_color_{i}', ''),
                    'logo': request.form.get(f'section_logo_{i}', '')
                }
            elif section_type == 'image':
                section = {
                    'type': 'image',
                    'src': request.form.get(f'section_src_{i}', ''),
                    'jump': request.form.get(f'section_jump_{i}', '')
                }
            elif section_type == 'video':
                section = {
                    'type': 'video',
                    'src': request.form.get(f'section_src_{i}', ''),
                    'poster': request.form.get(f'section_poster_{i}', '')
                }
            elif section_type == 'grid':
                images = []
                image_count = int(request.form.get(f'image_count_{i}', '0'))
                for j in range(image_count):
                    image = {
                        'src': request.form.get(f'image_src_{i}_{j}', ''),
                        'jump': request.form.get(f'image_jump_{i}_{j}', '')
                    }
                    images.append(image)
                section = {
                    'type': 'grid',
                    'images': images
                }
            elif section_type == 'contact':
                section = {
                    'type': 'contact',
                    'bgTheme': request.form.get(f'contact_bgTheme_{i}', 'theme-purple-pink'),
                    'contentTheme': request.form.get(f'contact_contentTheme_{i}', 'theme-purple-pink'),
                    'name': request.form.get(f'contact_name_{i}', ''),
                    'title': request.form.get(f'contact_title_{i}', ''),
                    'title2': request.form.get(f'contact_title2_{i}', ''),
                    'phone': request.form.get(f'contact_phone_{i}', ''),
                    'email': request.form.get(f'contact_email_{i}', ''),
                    'logo': request.form.get(f'contact_logo_{i}', ''),
                    'company': request.form.get(f'contact_company_{i}', ''),
                    'address': request.form.get(f'contact_address_{i}', '')
                }
            elif section_type == 'notice':
                section = {
                    'type': 'notice',
                    'title': request.form.get(f'notice_title_{i}', ''),
                    'content': request.form.get(f'notice_content_{i}', ''),
                    'tag': request.form.get(f'notice_tag_{i}', ''),
                    'autoPopup': request.form.get(f'notice_autoPopup_{i}') == 'on'
                }
            else:
                print(f"跳过区块 {i}: 未知类型 {section_type}")
                continue
            
            sections.append(section)
            print(f"添加区块: {section}")
        
        print(f"最终区块列表: {sections}")
        page['sections'] = sections
        save_config(config)
        print(f"保存配置成功")
        flash('内容区块保存成功')
        return redirect(url_for('pages'))
    
    return render_template('edit_sections.html', page=page, sections=page.get('sections', []))

# 上传资源
@app.route('/admin/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Debug logging
        print(f"Upload request received")
        print(f"Files in request: {list(request.files.keys())}")
        
        # Check if file is present in request
        if 'file' not in request.files:
            print("ERROR: No 'file' key in request.files")
            flash('没有文件上传')
            return redirect(request.url)
        
        file = request.files['file']
        print(f"File object: {file}")
        print(f"File filename: {file.filename}")
        
        # Check if file has a name
        if file.filename == '':
            print("ERROR: Empty filename")
            flash('没有选择文件')
            return redirect(request.url)
        
        # Validate and save the file
        if file and allowed_file(file.filename):
            try:
                # Get file extension
                ext = os.path.splitext(file.filename)[1].lower()
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
                file_url = f"{current_domain}/uploads/{filename}"
                print(f"File URL: {file_url}")
                flash(f'文件上传成功！URL: {file_url}')
                return render_template('upload.html', file_url=file_url)
            except Exception as e:
                print(f"File upload error: {e}")
                import traceback
                traceback.print_exc()
                flash(f'文件上传失败：{str(e)}')
                return redirect(request.url)
        else:
            print("ERROR: File type not allowed")
            flash('不支持的文件类型，请使用 png, jpg, jpeg, gif, mp4 格式')
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
                if ext in ['.png', '.jpg', '.jpeg', '.gif']:
                    file_type = 'image'
                elif ext in ['.mp4']:
                    file_type = 'video'
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

# 静态文件服务
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    import os
    print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    print(f"File path: {filepath}")
    print(f"File exists: {os.path.exists(filepath)}")
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
