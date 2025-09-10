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
    r"^https://www\.dmm\.co\.jp",
    r"^https://fantia\.jp",
    r"^https://marshmallow-qa\.com",
    r"^https://www\.dlsite\.com",
    r"^https://hitomi\.la",
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
        img = img.resize(new_size, Image.Resampling.LANCZOS)

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

