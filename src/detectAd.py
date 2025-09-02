from typing import List, Optional, Set, TypeVar, Callable
from PIL import Image, ImageOps
import numpy as np
import re, os
from pyzbar.pyzbar import decode, ZBarSymbol

T = TypeVar("T")

# 二维码白名单
qr_code_white_list = [
    r"^https://[^.]+\.fanbox\.cc",
    r"^https://twitter\.com",
    r"^https://x\.com",
    r"^https://www\.pixiv\.net",
    r"^https://fantia\.jp",
    r"^https://marshmallow-qa\.com",
    r"^https://www\.dlsite\.com",
    r"^https://hitomi\.la",
]

# 广告文件名正则列表
ad_file_patterns_re = [
    re.compile(r'^zzz.*\.jpg$', re.IGNORECASE),
    re.compile(r'^zzz.*\.png$', re.IGNORECASE),
    re.compile(r'^zzz.*\.webp$', re.IGNORECASE),
    re.compile(r'^YZv5\.0\.png$', re.IGNORECASE),
    re.compile(r'脸肿汉化组招募', re.IGNORECASE),
    re.compile(r'.*_ZZZZ0.*\..*$', re.IGNORECASE),
    re.compile(r'.*_ZZZZ1.*\..*$', re.IGNORECASE),
    re.compile(r'.*_zzz.*\..*$', re.IGNORECASE),
    re.compile(r'無邪気漢化組招募圖_ver.*\.png$', re.IGNORECASE),
    re.compile(r'無邪気無修宇宙分組_ver.*\.png$', re.IGNORECASE),
    re.compile(r'^_.+\.jpg$', re.IGNORECASE),
]

# 判断是否彩色图片
def is_color_img(img: Image.Image) -> bool:
    arr = np.array(img)
    # 每隔 16 个像素采样
    for i in range(0, arr.shape[0]*arr.shape[1], 16):
        y, x = divmod(i, arr.shape[1])
        r, g, b = arr[y, x, :3]
        if r != g or r != b:
            return True
    return False

# 识别二维码
def get_qr_code(img: Image.Image) -> Optional[str]:
    try:
        decoded = decode(img, symbols=[ZBarSymbol.QRCODE])
        if not decoded:
            return None
        return decoded[0].data.decode("utf-8")
    except Exception:
        return None

# 判断广告页
def is_ad_img(img: Image.Image, logger=None) -> bool:
    # 强制转 RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 缩小大图提高识别速度
    MAX_DIM = 1024
    if max(img.width, img.height) > MAX_DIM:
        scale = MAX_DIM / max(img.width, img.height)
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    # 黑白图肯定不是广告
    if not is_color_img(img):
        if logger: logger.debug("图片为黑白，不是广告")
        else: print("[DEBUG] 图片为黑白，不是广告")
        return False

    # 转灰度二值化
    gray = ImageOps.grayscale(img)
    binary = gray.point(lambda p: 255 if p >= 200 else 0)

    # 全图识别二维码
    text = get_qr_code(binary)
    if logger: logger.debug(f"[DEBUG] 全图二维码识别结果: {text}")
    else: print(f"[DEBUG] 全图二维码识别结果: {text}")

    # 分块扫描
    if not text:
        w, h = img.width // 2, img.height // 2
        for sx, sy in [(w, h), (0, h), (w, 0), (0, 0)]:
            try:
                block = img.crop((sx, sy, sx + w, sy + h))
                text = get_qr_code(block)
                if logger: logger.debug(f"[DEBUG] 块({sx},{sy},{w},{h})二维码识别结果: {text}")
                else: print(f"[DEBUG] 块({sx},{sy},{w},{h})二维码识别结果: {text}")
                if text:
                    break
            except Exception as e:
                if logger: logger.debug(f"[DEBUG] 块({sx},{sy},{w},{h}) decode 异常: {e}")
                else: print(f"[DEBUG] 块({sx},{sy},{w},{h}) decode 异常: {e}")
                continue

    if text:
        matched = [reg for reg in qr_code_white_list if re.match(reg, text)]
        if logger: logger.debug(f"[DEBUG] 匹配到白名单: {matched}")
        else: print(f"[DEBUG] 匹配到白名单: {matched}")
        return all(not re.match(reg, text) for reg in qr_code_white_list)
    else:
        if logger: logger.debug("[DEBUG] 未识别到二维码，非广告")
        else: print("[DEBUG] 未识别到二维码，非广告")
        return False

# 获取广告页
def get_ad_page(
    lst: List[T],
    is_ad_page: Callable[[T], bool],
    filenames: Optional[List[str]] = None,
    logger=None,
    ad_list: Optional[Set[int]] = None,
) -> Set[int]:
    if ad_list is None:
        ad_list = set()

    normal_num = 0
    # 检查最后十张
    for i in range(len(lst)-1, max(len(lst)-10, 2), -1):
        if i in ad_list:
            continue
        # 先根据文件名正则匹配广告页
        if filenames:
            name = os.path.basename(filenames[i])
            if any(pat.search(name) for pat in ad_file_patterns_re):
                ad_list.add(i)
                if logger:
                    logger.debug(f"[DEBUG] 文件名匹配广告: {i} => {name}")
                else:
                    print(f"[DEBUG] 文件名匹配广告: {i} => {name}")
                continue  # 匹配到文件名就跳过二维码检测

        item = lst[i]
        if not item:
            break

        # 二维码检测广告
        is_ad = is_ad_page(item, logger)
        if is_ad:
            ad_list.add(i)
            if logger:
                logger.debug(f"[DEBUG] 二维码检测广告: {i} => {filenames[i] if filenames else 'img'}")
            else:
                print(f"[DEBUG] 二维码检测广告: {i} => {filenames[i] if filenames else 'img'}")
        # 找到连续三张正常漫画页后中断
        elif normal_num > 2:
            break
        else:
            normal_num += 1

    # 根据邻页规则补充广告
    ad_num = 0
    for i in range(min(ad_list, default=0), len(lst)):
        if i in ad_list:
            ad_num += 1
            continue
        # 连续两张广告后面的肯定也都是广告，夹在两张广告中间的肯定也是广告
        if ad_num >= 2 or ((i - 1 in ad_list) and (i + 1 in ad_list)):
            ad_list.add(i)
            if logger:
                logger.debug(f"[DEBUG] 根据邻页规则补充广告: {i} => {filenames[i] if filenames else 'img'}")
            else:
                print(f"[DEBUG] 根据邻页规则补充广告: {i} => {filenames[i] if filenames else 'img'}")
        else:
            ad_num = 0

    if logger:
        logger.info(f"[INFO] 最终广告页索引: {sorted(ad_list)}")
        if filenames:
            logger.info(f"[INFO] 最终广告页文件: {', '.join([filenames[i] for i in sorted(ad_list)])}")
    else:
        print(f"[INFO] 最终广告页索引: {sorted(ad_list)}")
        if filenames:
            print(f"[INFO] 最终广告页文件: {', '.join([filenames[i] for i in sorted(ad_list)])}")

    return ad_list
