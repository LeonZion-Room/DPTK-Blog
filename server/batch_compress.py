#!/usr/bin/env python3
"""批量压缩图片和PDF"""
import os
import sys
import shutil
from PIL import Image, UnidentifiedImageError
import fitz  # PyMuPDF
import io

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), '..', 'uploads')
ORIG_DIR = os.path.join(UPLOAD_DIR, 'upload-orig')

def compress_image(filepath):
    """PNG转JPG，压缩到约1/20大小"""
    if not os.path.exists(ORIG_DIR):
        os.makedirs(ORIG_DIR)
    
    filename = os.path.basename(filepath)
    orig_filepath = os.path.join(ORIG_DIR, filename)
    # 如果存在原始备份，先恢复
    if os.path.exists(orig_filepath):
        shutil.copy2(orig_filepath, filepath)
    else:
        shutil.copy2(filepath, orig_filepath)
    
    original_size = os.path.getsize(filepath)
    target_bytes = max(original_size // 10, 10240)  # 最少10KB
    
    try:
        img = Image.open(filepath)
        img.load()
    except (UnidentifiedImageError, OSError, IOError) as e:
        print(f"  [SKIP] {filename}: 损坏图片 ({e})")
        return False
    
    # 统一转为RGB
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
    
    # 如果已经很小，直接转JPG
    if original_size <= target_bytes:
        img.save(filepath, 'JPEG', quality=92, optimize=True)
        new_size = os.path.getsize(filepath)
        print(f"  [OK] {filename}: {original_size//1024}KB -> {new_size//1024}KB (已转JPG)")
        return True
    
    # 二分法压缩 + 必要时缩小尺寸
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
    
    # 最终保存
    if scale < 1.0:
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        resized.save(filepath, 'JPEG', quality=best_quality, optimize=True)
    else:
        img.save(filepath, 'JPEG', quality=best_quality, optimize=True)
    
    new_size = os.path.getsize(filepath)
    ratio = original_size / max(new_size, 1)
    print(f"  [OK] {filename}: {original_size//1024}KB -> {new_size//1024}KB (1/{ratio:.0f})")
    return True


def compress_pdf(filepath):
    """PDF转纯图PDF，按大小规则压缩"""
    if not os.path.exists(ORIG_DIR):
        os.makedirs(ORIG_DIR)
    
    filename = os.path.basename(filepath)
    orig_filepath = os.path.join(ORIG_DIR, filename)
    # 如果存在原始备份，先恢复
    if os.path.exists(orig_filepath):
        shutil.copy2(orig_filepath, filepath)
    else:
        shutil.copy2(filepath, orig_filepath)
    
    original_size = os.path.getsize(filepath)
    # 按大小规则确定目标大小
    if original_size > 10 * 1024 * 1024:  # >10MB → 7MB
        target_bytes = 7 * 1024 * 1024
    elif original_size > 5 * 1024 * 1024:  # 5-10MB → 3MB
        target_bytes = 3 * 1024 * 1024
    else:  # <5MB → 保留原大小，不压缩
        print(f"  [SKIP] {filename}: {original_size//1024}KB < 5MB，保留原大小")
        return True
    
    try:
        doc = fitz.open(filepath)
        num_pages = len(doc)
    except Exception as e:
        print(f"  [SKIP] {filename}: 无法打开PDF ({e})")
        return False
    
    # 动态调整DPI
    target_dpi = 150
    pdf_images = []
    
    for _ in range(5):  # 最多尝试5次降DPI
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
    
    # 生成纯图片PDF
    output_pdf = filepath + '.tmp'
    pil_images = []
    for img_bytes, w, h in pdf_images:
        pil_img = Image.open(io.BytesIO(img_bytes))
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
        blank = Image.new('RGB', (595, 842), (255, 255, 255))
        blank.save(output_pdf, 'PDF', resolution=target_dpi)
    
    shutil.move(output_pdf, filepath)
    
    new_size = os.path.getsize(filepath)
    ratio = original_size / max(new_size, 1)
    print(f"  [OK] {filename}: {original_size//1024}KB -> {new_size//1024}KB (1/{ratio:.0f}, {target_dpi}DPI)")
    return True


def main():
    if not os.path.exists(UPLOAD_DIR):
        print(f"上传目录不存在: {UPLOAD_DIR}")
        sys.exit(1)
    
    # 收集所有文件
    png_files = []
    pdf_files = []
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith('.') or f == 'upload-orig':
            continue
        filepath = os.path.join(UPLOAD_DIR, f)
        if not os.path.isfile(filepath):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext == '.png':
            png_files.append(filepath)
        elif ext == '.pdf':
            pdf_files.append(filepath)
    
    print(f"找到 {len(png_files)} 个PNG文件, {len(pdf_files)} 个PDF文件")
    print(f"原始文件将备份到: {ORIG_DIR}")
    print()
    
    # 压缩PNG
    print("=" * 60)
    print("压缩PNG图片 (PNG→JPG, 1/10大小)")
    print("=" * 60)
    png_ok = 0
    for i, fp in enumerate(sorted(png_files), 1):
        print(f"[{i}/{len(png_files)}]", end=" ")
        if compress_image(fp):
            png_ok += 1
    
    print()
    print(f"PNG完成: {png_ok}/{len(png_files)}")
    
    # 压缩PDF
    print()
    print("=" * 60)
    print("压缩PDF (纯图PDF, 1/10大小)")
    print("=" * 60)
    pdf_ok = 0
    for i, fp in enumerate(sorted(pdf_files), 1):
        print(f"[{i}/{len(pdf_files)}]", end=" ")
        if compress_pdf(fp):
            pdf_ok += 1
    
    print()
    print(f"PDF完成: {pdf_ok}/{len(pdf_files)}")
    
    # 总大小
    total = sum(os.path.getsize(os.path.join(UPLOAD_DIR, f)) 
                for f in os.listdir(UPLOAD_DIR) 
                if os.path.isfile(os.path.join(UPLOAD_DIR, f)) and f != 'upload-orig')
    print(f"\n压缩后 uploads 总大小: {total/1024/1024:.1f}MB")


if __name__ == '__main__':
    main()