#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信分享卡片图片生成器
生成与微信名片页面风格一致的分享卡片图片
"""

import io
import os
import hashlib
import json
import requests
from PIL import Image, ImageDraw, ImageFont

# 字体路径
FONT_DIR = '/usr/share/fonts/opentype/noto'
FONT_BOLD = os.path.join(FONT_DIR, 'NotoSansCJK-Bold.ttc')
FONT_REGULAR = os.path.join(FONT_DIR, 'NotoSansCJK-Regular.ttc')
FONT_FALLBACK = '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'share_card_cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# 卡片尺寸 (微信分享推荐 1:1 或更大)
CARD_WIDTH = 500
CARD_HEIGHT = 500

# 渐变背景色 (蓝到金)
BG_TOP = (70, 130, 180)
BG_BOTTOM = (210, 180, 100)


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c * 2 for c in hex_color])
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def load_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype(FONT_FALLBACK, size)
        except Exception:
            return ImageFont.load_default()


def download_image(url, timeout=5):
    try:
        if url.startswith('http'):
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert('RGBA')
        elif os.path.exists(url):
            return Image.open(url).convert('RGBA')
    except Exception:
        pass
    return None


def create_gradient_bg(width, height, color_top, color_bottom):
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img


def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + radius * 2, y0 + radius * 2], 180, 270, fill=fill)
    draw.pieslice([x1 - radius * 2, y0, x1, y0 + radius * 2], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - radius * 2, x0 + radius * 2, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - radius * 2, y1 - radius * 2, x1, y1], 0, 90, fill=fill)


def generate_share_card(info, cache_key=None):
    name = info.get('name', '')
    phone = info.get('phone', '')
    title = info.get('title', '')
    title2 = info.get('title2', '')
    email = info.get('email', '')
    logo_url = info.get('logo', '')

    if cache_key:
        cache_file = os.path.join(CACHE_DIR, f'{cache_key}.png')
        if os.path.exists(cache_file):
            return cache_file

    # 创建渐变背景（填满整个图片）
    bg = create_gradient_bg(CARD_WIDTH, CARD_HEIGHT, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(bg)

    # 内容区域（留出小边距）
    padding = 30
    content_x = padding
    content_y = padding
    content_w = CARD_WIDTH - padding * 2
    content_h = CARD_HEIGHT - padding * 2
    center_x = content_x + content_w // 2

    # 内容从中间偏下开始，占据更多空间
    current_y = content_y + 100

    # Logo - 居中显示，更大
    logo_size = 100
    logo_img = None
    if logo_url:
        logo_img = download_image(logo_url)

    if logo_img:
        logo_img = logo_img.resize((logo_size, logo_size), Image.LANCZOS)
        # 创建圆形遮罩
        mask = Image.new('L', (logo_size, logo_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, logo_size, logo_size], fill=255)
        # 创建白色圆形背景
        circle_bg = Image.new('RGBA', (logo_size + 10, logo_size + 10), (255, 255, 255, 255))
        circle_mask = Image.new('L', (logo_size + 10, logo_size + 10), 0)
        circle_draw = ImageDraw.Draw(circle_mask)
        circle_draw.ellipse([0, 0, logo_size + 10, logo_size + 10], fill=255)
        # 粘贴logo到白色圆形背景
        circle_bg.paste(logo_img, (5, 5), mask)
        # 粘贴到主图
        logo_x = center_x - (logo_size + 10) // 2
        bg.paste(circle_bg, (logo_x, current_y), circle_mask)
    else:
        # 绘制白色圆形占位符
        draw.ellipse([center_x - logo_size // 2, current_y, center_x + logo_size // 2, current_y + logo_size], fill=(255, 255, 255))

    current_y += logo_size + 25

    # Name - 居中，大号字体
    if name:
        font_name = load_font(42, bold=True)
        bbox = draw.textbbox((0, 0), name, font=font_name)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((center_x - text_w // 2, current_y), name, fill=(255, 255, 255), font=font_name)
        current_y += text_h + 10

    # Phone - 居中
    if phone:
        font_phone = load_font(32, bold=True)
        bbox = draw.textbbox((0, 0), phone, font=font_phone)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((center_x - text_w // 2, current_y), phone, fill=(255, 255, 255), font=font_phone)
        current_y += text_h + 15

    # Title - 居中，较小字体
    if title:
        font_title = load_font(22)
        bbox = draw.textbbox((0, 0), title, font=font_title)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((center_x - text_w // 2, current_y), title, fill=(255, 255, 255, 230), font=font_title)
        current_y += text_h + 5

    # Title2 - 居中
    if title2:
        font_title2 = load_font(22)
        bbox = draw.textbbox((0, 0), title2, font=font_title2)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((center_x - text_w // 2, current_y), title2, fill=(255, 255, 255, 230), font=font_title2)
        current_y += text_h + 5

    # Email - 居中
    if email:
        font_email = load_font(20)
        email_text = f'邮箱：{email}'
        bbox = draw.textbbox((0, 0), email_text, font=font_email)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((center_x - text_w // 2, current_y), email_text, fill=(255, 255, 255, 210), font=font_email)
        current_y += text_h + 25

    # Buttons - 白色背景，深色文字
    btn_y = content_y + content_h - 70
    btn_h = 44
    btn_radius = 22
    btn_gap = 12
    btn_w = (content_w - btn_gap * 2) // 3

    buttons = [
        ('推荐给TA', (255, 255, 255)),
        ('保存到手机', (255, 255, 255)),
        ('一键拨号', (255, 255, 255)),
    ]

    for i, (text, color) in enumerate(buttons):
        btn_x = content_x + i * (btn_w + btn_gap)
        draw_rounded_rect(draw, [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], btn_radius, color)
        font_btn = load_font(16, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font_btn)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (btn_x + (btn_w - tw) // 2, btn_y + (btn_h - th) // 2 - 1),
            text, fill=(50, 50, 50), font=font_btn
        )

    if cache_key:
        bg.save(cache_file, 'PNG')
        return cache_file

    buf = io.BytesIO()
    bg.save(buf, 'PNG')
    buf.seek(0)
    return buf


def get_cache_key(info):
    raw = json.dumps(info, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()
