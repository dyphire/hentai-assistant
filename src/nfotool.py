import zipfile, os, shutil
import io
from xml.dom.minidom import parseString
import dicttoxml
from utils import check_dirs

def make_comicinfo_xml(metadata):
    return parseString(dicttoxml.dicttoxml(metadata, custom_root='ComicInfo', attr_type=False)).toprettyxml(indent="  ", encoding="UTF-8")

# 将XML直接写入ZIP文件中
def write_xml_to_zip(zip_file_path, metadata, copy=False, logger=None):
    # 创建XML内容
    xml_content = make_comicinfo_xml(metadata)      
    
    if copy == False:
        # 未指定输出路径, 直接对原文档进行修改
        # 创建临时内存缓冲区
        temp_zip_buffer = io.BytesIO()

        # 打开现有的 ZIP 文件进行读取，并创建一个临时 ZIP 文件
        with zipfile.ZipFile(zip_file_path, 'r') as existing_zip:
            if "ComicInfo.xml" in existing_zip.namelist():
                if logger: logger.info('已经存在 ComicInfo.xml, 即将替换为新的内容')
                overwrite = True
                # 打开内存中的新 ZIP 文件
                with zipfile.ZipFile(temp_zip_buffer, 'w') as new_zip:
                    # 遍历现有 ZIP 文件中的所有文件
                    for item in existing_zip.infolist():
                        # 如果不是要替换的 XML 文件，写入新 ZIP 文件
                        if item.filename != "ComicInfo.xml":
                            new_zip.writestr(item, existing_zip.read(item.filename))
                    # 将新的 XML 内容写入 ZIP 文件，覆盖原来的文件
                    new_zip.writestr("ComicInfo.xml", xml_content)
            else: overwrite = False
        if overwrite == True:
            # 将内存中的 ZIP 文件内容保存回原来的文件路径，覆盖原来的 ZIP 文件
            with open(zip_file_path, 'wb') as f:
                f.write(temp_zip_buffer.getvalue())
        else:
            # 将XML内容写入zip文件
            with zipfile.ZipFile(zip_file_path, 'a', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("ComicInfo.xml", xml_content)
        if logger: logger.info("ComicInfo.xml 写入完毕")
            
    else: # 重新生成一个新的cbz文件
        zip_file_root = os.path.dirname(zip_file_path)
        zip_file_name = os.path.basename(zip_file_path)
        target_zip = os.path.join(zip_file_root, zip_file_name.rsplit('.', 1)[0] + '.tmp') # 防止撞名,先使用临时文件名,待迁移旧档案后,再进行重命名
        # 打开现有的压缩包进行读取
        with zipfile.ZipFile(zip_file_path, 'r') as src_zip:
            # 创建一个新的压缩包
            with zipfile.ZipFile(target_zip, 'w') as tgt_zip:
                # 复制原始压缩包中的所有文件到新压缩包中
                for file_info in src_zip.infolist():
                    file_data = src_zip.read(file_info.filename)
                    tgt_zip.writestr(file_info, file_data)
                # 添加新的文本文件到新压缩包中
                tgt_zip.writestr("ComicInfo.xml", xml_content)

        # 清理旧档案
        try:
            completed_path = os.path.join(zip_file_root, 'Completed')
            os.renames(zip_file_path, os.path.join(check_dirs(completed_path), zip_file_name))
        except Exception as e:
            if logger: logger.error(e)
            
        # 为新档命名
        new_file_path = target_zip.replace('.tmp', '.cbz')
        os.rename(target_zip, new_file_path)
        return new_file_path


