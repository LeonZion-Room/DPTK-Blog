import os
import json
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='templates', static_folder='static')

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ASSETS_DIR = os.path.join(DATA_DIR, 'assets')
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'db.json')

DEFAULT_DB = {
    "components": [
        {
            "uid": "sec_profile_01",
            "type": "profile",
            "name": "个人名片头部",
            "data": {
                "avatar": "/static/assets/default_avatar.png",
                "name": "李俊锋",
                "title": "高级技术总监 & 解决方案专家",
                "company": "大鹏投控 / 智慧机房事业部",
                "phone": "13800138000",
                "email": "lijunfeng@leyon.top",
                "bgImage": "/static/assets/default_bg.jpg"
            }
        },
        {
            "uid": "sec_tabs_01",
            "type": "tabs",
            "name": "多标签分类导航",
            "data": {
                "activeTab": "tab1",
                "tabs": [
                    {
                        "id": "tab1",
                        "title": "业务介绍",
                        "children": [
                            {
                                "uid": "sec_intro_01",
                                "type": "text",
                                "name": "业务简介",
                                "data": {
                                    "title": "智慧机房与投控数字化建设",
                                    "content": "专注于机房自动化巡检、SecOps 闭环、大屏可视化设计及企业数字化转型。",
                                    "image": "/static/assets/intro_banner.png"
                                }
                            }
                        ]
                    },
                    {
                        "id": "tab2",
                        "title": "产品案例",
                        "children": [
                            {
                                "uid": "sec_case_01",
                                "type": "card",
                                "name": "案例卡片",
                                "data": {
                                    "title": "LZ-Agent 自动化运维中心",
                                    "desc": "支持 SSH 跨节点执行器、工单系统、定时巡检。",
                                    "logo": "/static/assets/case_logo.png",
                                    "jumpUrl": "#"
                                }
                            }
                        ]
                    }
                ]
            }
        }
    ],
    "mapping": ["sec_profile_01", "sec_tabs_01"]
}

def load_db():
    if not os.path.exists(DB_PATH):
        save_db(DEFAULT_DB)
    try:
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_DB

def save_db(data):
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/')
@app.route('/index-dynamic.html')
def index():
    # Token verification
    token = request.args.get('token', '')
    valid_token = 'wswwsw1234'
    
    if token != valid_token:
        return render_template('access_denied.html')
    
    full_path = request.full_path or ''
    is_dev = 'dev=1' in full_path or 'mode=dev' in full_path or request.args.get('dev') == '1'
    page_id = request.args.get('page', 'default')
    db = load_db()
    return render_template('index-dynamic.html', components=db['components'], mapping=db['mapping'], is_dev=is_dev, page_id=page_id)

@app.route('/admin')
def admin():
    db = load_db()
    return render_template('admin.html', db=db)

@app.route('/admin/group/<group_id>')
def admin_group(group_id):
    db = load_db()
    group = None
    for page in db.get('pages', []):
        if page.get('id') == group_id:
            group = page
            break
    if not group:
        return redirect('/admin')
    return render_template('group_edit.html', group=group, group_id=group_id)

@app.route('/admin/resource-replace')
def resource_replace_page():
    return render_template('resource_replace.html')

@app.route('/api/components', methods=['GET', 'POST'])
def api_components():
    db = load_db()
    if request.method == 'GET':
        return jsonify({"code": 0, "data": db})
    else:
        req_data = request.json
        if not req_data:
            return jsonify({"code": 400, "msg": "Invalid JSON"}), 400
        db['components'] = req_data.get('components', db['components'])
        db['mapping'] = req_data.get('mapping', db['mapping'])
        save_db(db)
        return jsonify({"code": 0, "msg": "Success"})

def collect_resources_recursive(obj, resources=None):
    if resources is None:
        resources = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ('avatar', 'bgImage', 'image', 'logo', 'icon', 'customBgImage', 'share_icon') and isinstance(v, str) and v:
                resources.append(v)
            elif isinstance(v, (dict, list)):
                collect_resources_recursive(v, resources)
    elif isinstance(obj, list):
        for item in obj:
            collect_resources_recursive(item, resources)
    return resources

def find_references_recursive(obj, target_str, current_uid=None, refs=None):
    if refs is None:
        refs = []
    if isinstance(obj, dict):
        uid = obj.get('uid', current_uid)
        name = obj.get('name', obj.get('type', '未知组件'))
        has_match = False
        for k, v in obj.items():
            if isinstance(v, str) and target_str in v:
                has_match = True
            elif isinstance(v, (dict, list)):
                find_references_recursive(v, target_str, uid, refs)
        if has_match and uid and not any(r['uid'] == uid for r in refs):
            refs.append({"uid": uid, "name": name, "type": obj.get('type', 'unknown')})
    elif isinstance(obj, list):
        for item in obj:
            find_references_recursive(item, target_str, current_uid, refs)
    return refs

@app.route('/api/resource/references', methods=['GET'])
def api_resource_references():
    link = request.args.get('link', '')
    filename = request.args.get('filename', '')
    target = link or filename
    if not target:
        return jsonify({"code": 400, "msg": "Missing link or filename"}), 400
    
    db = load_db()
    refs = find_references_recursive(db['components'], target)
    return jsonify({"code": 0, "references": refs})

@app.route('/api/resource/replace', methods=['POST'])
def api_resource_replace():
    if 'file' not in request.files:
        return jsonify({"code": 400, "msg": "No file uploaded"}), 400
    file = request.files['file']
    link = request.form.get('link', '')
    filename = request.form.get('filename', '')
    
    if not filename and link:
        filename = os.path.basename(link.split('?')[0])
    
    if not filename:
        filename = secure_filename(file.filename)
    else:
        filename = secure_filename(filename)
        
    save_path = os.path.join(ASSETS_DIR, filename)
    file.save(save_path)
    
    file_url = f"/static/assets/{filename}"
    return jsonify({"code": 0, "msg": "Resource replaced successfully", "url": file_url, "filename": filename})

@app.route('/static/assets/<path:filename>')
def uploaded_asset(filename):
    return send_from_directory(ASSETS_DIR, filename)

@app.route('/api/contact-vcard')
def contact_vcard():
    vcf_content = """BEGIN:VCARD
VERSION:3.0
FN:李俊锋
N:李;俊锋;;;
TITLE:高级技术总监 & 解决方案专家
ORG:大鹏投控 / 智慧机房事业部
TEL;TYPE=CELL:13800138000
EMAIL:lijunfeng@leyon.top
URL:http://119.145.17.34:8000
END:VCARD
"""
    return Response(
        vcf_content.encode('utf-8'),
        mimetype='text/vcard',
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''%E6%9D%8e%E4%BF%8a%E9%94%8b.vcf"
        }
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
