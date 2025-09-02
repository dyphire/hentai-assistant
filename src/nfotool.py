import zipfile, os
import io
import shutil
from xml.dom.minidom import parseString
import dicttoxml
from utils import check_dirs
from PIL import Image
from natsort import natsorted
import detectAd

def make_comicinfo_xml(metadata):
    return parseString(
        dicttoxml.dicttoxml(metadata, custom_root='ComicInfo', attr_type=False)
    ).toprettyxml(indent="  ", encoding="UTF-8")

def write_xml_to_zip(zip_file_path, mapped_file_path, metadata, app=None, logger=None):
    zip_file_root = os.path.dirname(zip_file_path)
    zip_file_name = os.path.basename(zip_file_path)
    copy = app and app.config.get('keep_original_file', False)
    remove_ad_flag = app and app.config.get('remove_ads', False)

    print(f"处理文件: {zip_file_path}, 复制原文件: {copy}, 删除广告页: {remove_ad_flag}")
    if logger: logger.info(f"处理文件: {zip_file_path}, 复制原文件: {copy}, 删除广告页: {remove_ad_flag}")

    xml_content = make_comicinfo_xml(metadata)

    # 目标 ZIP
    if copy:
        target_zip_path = os.path.join(zip_file_root, zip_file_name.rsplit('.', 1)[0] + '.tmp')
        zip_buffer = target_zip_path  # 用作物理文件路径
    else:
        zip_buffer = io.BytesIO()     # 内存缓冲覆盖原文件

    # 读取原 ZIP 并写入目标 ZIP
    with zipfile.ZipFile(zip_file_path, 'r') as src_zip, \
         zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as tgt_zip:

        # 获取所有图片并自然排序
        img_files = [f for f in src_zip.namelist() if f.lower().endswith(
            ('.jpg', '.jpeg', '.png', '.webp', '.avif', '.jxl')
        )]
        img_files = natsorted(img_files, key=lambda name: os.path.basename(name))

        # 加载图片对象，保留在 img_objs
        img_objs = []
        for name in img_files:
            with src_zip.open(name) as f:
                img = Image.open(f)
                img.load()
                img_objs.append(img)

        # 广告页检测
        ad_pages = set()
        if remove_ad_flag:
            if logger: logger.info("正在检测广告页...")
            ad_list = detectAd.get_ad_page(img_objs, detectAd.is_ad_img, img_files, logger=logger)
            ad_pages = set(ad_list)
            if ad_pages:
                print(f"广告页已删除: {', '.join([img_files[i] for i in ad_pages])}")
                if logger: logger.info(f"广告页已删除: {', '.join([img_files[i] for i in ad_pages])}")

        # 写入非广告页
        for idx, name in enumerate(img_files):
            if idx in ad_pages:
                continue
            tgt_zip.writestr(name, src_zip.read(name))

        # 写入 ComicInfo.xml
        tgt_zip.writestr("ComicInfo.xml", xml_content)

    # 保存文件
    if copy:
        # 移动原文件到 Completed
        try:
            completed_path = os.path.join(zip_file_root, 'Completed')
            os.renames(zip_file_path, os.path.join(check_dirs(completed_path), zip_file_name))
        except Exception as e:
            if logger: logger.error(e)

        new_file_path = target_zip_path.replace('.tmp', '.cbz')
        os.rename(target_zip_path, new_file_path)
    else:
        # 内存缓冲写回原文件
        with open(zip_file_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
        new_file_path = zip_file_path

    # 移动到映射目录
    mapped_file_path = os.path.splitext(mapped_file_path)[0] + '.cbz'
    if mapped_file_path != new_file_path:
        os.makedirs(os.path.dirname(mapped_file_path), exist_ok=True)
        shutil.move(new_file_path, mapped_file_path)
        if logger: logger.info(f"文件移动到映射目录: {mapped_file_path}")
        print(f"文件移动到映射目录: {mapped_file_path}")
        return mapped_file_path

    return new_file_path
