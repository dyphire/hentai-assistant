import re
import html
import langcodes

from openai_helper import OpenAIHelper
from providers import ehentai
from utils import chinese_number_to_arabic

def normalize_tilde(filename: str) -> str:
    filename = re.sub(r'([话話])(?!\s)', r'\1 ', filename)
    filename = re.sub(r'([~⁓～—_「-])', ' ', filename)
    return filename

def extract_number_from_match(text: str) -> str:
    """
    从匹配到的文本中提取数字(阿拉伯数字或中文数字)
    返回字符串形式的阿拉伯数字,如果无法提取则返回 None
    """
    # 优先匹配阿拉伯数字(支持小数)
    arabic_match = re.search(r'\d+(?:\.\d+)?', text)
    if arabic_match:
        return arabic_match.group(0)
    
    # 尝试匹配中文数字
    chinese_match = re.search(r'[一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]+', text)
    if chinese_match:
        return chinese_number_to_arabic(chinese_match.group(0))
    
    return None

def clean_name(title):
    name = re.sub(r'[\s\-—_:：•·․,，。\'’?？!！~⁓～]+$', '', title)
    return name.strip()

def find_translator(title):
    keywords = r"(?:汉化|漢化|翻译|翻譯|机翻|機翻|渣翻|个汉|個漢)"
    
    # 规则A: 匹配所有括号内的情况
    pattern_a = rf"[\[\(【]([^\]\)】]*?{keywords}[^\]\)】]*)[\]\)】]"
    
    # 规则B: 匹配空格后、且不以括号开头的情况
    pattern_b = rf"\s+([^\[\(【\]\)】\s]*{keywords}[^\[\(【\]\)】\s]*)"

    pattern = f"{pattern_a}|{pattern_b}"

    match = re.search(pattern, title)

    if match:
        # 逻辑不变：group(1) 对应规则A，group(2) 对应规则B
        result = match.group(1) or match.group(2)
        return result.strip()
    return None

def add_tag_to_front(comicinfo, new_tag: str):
    new_tag = new_tag.strip().lower()
    if not new_tag:
        return
    if 'Tags' in comicinfo and comicinfo['Tags']:
        tags = [t.strip() for t in comicinfo['Tags'].split(',') if t.strip()]
        if new_tag not in tags:
            tags.insert(0, new_tag)
        comicinfo['Tags'] = ', '.join(tags)
    else:
        comicinfo['Tags'] = new_tag
        
def parse_filename(text, translator):
    # 去除所有括号内的内容, 将清理后的文本作为标题
    title = re.sub(r'\[.*?\]|\(.*?\)', '', text).strip()
    print(f'从文件名{text}中解析到 Title:', title)
    # 提取同人志的原作信息
    # parody = extract_parody(text, translator)

    # 找到 title 在原始 text 中的起始位置
    title_start = text.find(title)
    # 截取 title 前的文本
    before_title = text[:title_start]
    # 匹配紧挨标题的前一个 [] 内的内容，在 EH 的命名规范中，它总是代表作者信息
    search_author = re.search(r'\[([^\]]+)\]\s*$', before_title)

    if not search_author == None:
        search_writer = re.search(r'(.+?)\s*\((.+?)\)', search_author.group(1))
        # 判断作者和画师
        if not search_writer == None:
            writer = search_writer.group(1) # 同人志的情况下，把社团视为 writer
            penciller = search_writer.group(2) # 把该漫画的作者视为 penciller
        else:
            writer = penciller = search_author.group(1)
        # 有时候也会在作者信息中著名原著作者, 尝试去分离信息, 并将原著作者与社团共同视为 writer
        for s in [ '、', ',']:
            if s in penciller:
                parts = penciller.split(s)
                if len(parts) > 1:
                    writer = writer + ', ' + parts[0]
                    print('\nWriter:', writer)
                    penciller = parts[1]
                    print('Penciller:', penciller)
        return title, writer, penciller
    else:
        return title, None, None

class MetadataExtractor:
    def __init__(self, config, eh_translator):
        self.config = config
        self.translator = eh_translator

    def extract_before_chapter(self, filename, logger=None):
        patterns = [
            # 1 中文/阿拉伯数字
            r'(.*?)第?\s*[一二三四五六七八九十\d]+\s*[卷巻话話回迴編篇章册冊席期辑輯节節部]',
            # 2. 数字在前，关键字在后
            r'(.*?)\d+\s*[卷巻话話回迴編篇章册冊席期辑輯节節部]',
            # 3. 关键字在前，数字在后
            r'(.*?)[卷巻回迴編篇章册冊席期辑輯节節部]\s*[一二三四五六七八九十\d]+',
            # 4. Vol/Vol./vol/v/V + 数字
            r'(.*?)\s*(?:vol|v|#|＃)[\s\.]*\d+',
            # 5. 圆方括号+数字
            r'(.*?)\s*[\[\(（]\d+[\]\)）]\s*$',
            # 6. 上中下前后
            r'^(.*?)(?:[上中下前后後](?:編|回)|[上中下前后後]\s*$)',
            # 7. 纯数字
            r'(.*?)\s*\d+(\s|$)',
        ]

        filename = normalize_tilde(filename)
        for i, pat in enumerate(patterns):
            m = re.search(pat, filename, re.I)
            if m:
                series_name = clean_name(m.group(1)).strip()
                
                # 模式 6 (上中下前后) 不提取数字
                if i == 5:
                    return series_name, None
                
                # 从原始 filename 中,去掉 series_name 后的剩余部分提取数字
                # 这样可以避免正则匹配范围不足的问题
                series_end_pos = filename.find(series_name) + len(series_name)
                remaining_text = filename[series_end_pos:]
                number = extract_number_from_match(remaining_text)
                
                return series_name, number
        
        return None, None
            
    def get_series_for_multi_work_series(self, filename, logger=None):
        filename = normalize_tilde(filename)
        # 如果配置了 OpenAI ，先尝试使用 AI 进行识别
        use_openai = self.config.get('OPENAI_SERIES_DETECTION') and self.config.get('OPENAI_TOGGLE')
        
        if use_openai:
            if logger: logger.info("正在为无法识别章节号的文件名调用 OpenAI 进行识别...")
            helper = OpenAIHelper(
                api_key=self.config.get('OPENAI_API_KEY'),
                base_url=self.config.get('OPENAI_BASE_URL'),
                model=self.config.get('OPENAI_MODEL'),
                logger=logger
            )
            openai_result = helper.query(filename)

            # 检查返回是否有效 (query 失败时返回 None)
            if openai_result and openai_result.get('series'):
                if logger: logger.info(f"识别结果为: {openai_result}")
                series = openai_result.get('series')
                number = openai_result.get('number')
                return series, number
        
        # 如果没有匹配任何章节模式 → 返回第一个空格前的内容
        is_aggressive_series_detection = self.config.get('AGGRESSIVE_SERIES_DETECTION', False)
        if is_aggressive_series_detection:
            filename = filename.strip()
            idx = filename.find(' ')
            if idx == -1:
                return clean_name(filename).strip(), None
            return clean_name(filename[:idx]).strip(), None
        
        return None, None
        
    def fill_field(self, comicinfo, field, tags, prefixes):
        for prefix in prefixes:
            values = []
            for t in tags:
                if t.startswith(f"{prefix}:"):
                    name = t[len(prefix)+1:]
                    name = self.translator.get_translation(name, prefix)
                    values.append(name)
            if values:
                comicinfo[field] = ", ".join(values)
                return

    def parse_eh_tags(self, tags):
        comicinfo = {'AgeRating':'R18+'}
        tag_list = []
        for tag in tags:
            matchTag = re.match(r'(.+?):(.*)',tag)
            if matchTag:
                namespace = matchTag.group(1).lower()
                tag_name = matchTag.group(2).lower()
                if namespace == 'language':
                    if tag_name not in ['translated', 'rewrite']:
                        lang_obj = langcodes.find(tag_name)
                        if lang_obj:
                            comicinfo['LanguageISO'] = lang_obj.language
                elif namespace == 'parody':
                    if tag_name not in ['original', 'various']:
                        tag_name = self.translator.get_translation(tag_name, namespace)
                        tag_list.append(f"{namespace}:{tag_name}")
                elif namespace in ['character']:
                    tag_name = self.translator.get_translation(tag_name, namespace)
                    tag_list.append(f"{namespace}:{tag_name}")
                elif namespace == 'female' or namespace == 'mixed' or namespace == 'location':
                    tag_name = self.translator.get_translation(tag_name, namespace)
                    tag_list.append(tag_name)
                elif namespace == 'male':
                    m_list = ehentai.male_only_taglist()
                    if m_list and tag_name in m_list:
                        tag_name = self.translator.get_translation(tag_name, namespace)
                        tag_list.append(tag_name)
                elif namespace == 'other' or namespace == 'tag':
                    if tag_name not in ['extraneous ads',  'already uploaded', 'missing cover', 'forbidden content', 'replaced', 'compilation', 'incomplete', 'caption']:
                        if namespace == 'tag':
                            tag_name = self.translator.get_translation(tag_name)
                        else:
                            tag_name = self.translator.get_translation(tag_name, namespace)
                        tag_list.append(tag_name)
        
        tag_list_sorted = sorted(set(tag_list), key=tag_list.index)
        if not 'webtoon' in tag_list_sorted:
            comicinfo['Manga'] = 'YesAndRightToLeft'
        comicinfo['Tags'] = ', '.join(tag_list_sorted)
        return comicinfo

    def parse_gmetadata(self, data, logger=None):
        comicinfo = {}
        if 'tags' in data:
            comicinfo.update(self.parse_eh_tags(data['tags']))
        
        if not data.get('category', '').lower() == 'non-h':
            comicinfo['Genre'] = 'Hentai'
        if data.get('category', '').lower() not in ['manga', 'misc', 'asianporn', 'private']:
            comicinfo['category'] = self.translator.get_translation(data.get('category', ''), 'reclass')
        
        if self.config.get('PREFER_JAPANESE_TITLE') and data.get('title_jpn'):
            text = html.unescape(data['title_jpn'])
        else:
            text = html.unescape(data.get('title', ''))
        comicinfo['OriginalTitle'] = text   
            
        comic_market = re.search(r'\(C(\d+)\)', text)
        if comic_market:
           add_tag_to_front(comicinfo, f"c{comic_market.group(1)}")
        
        if data.get('category', '').lower() not in ['imageset']:
            comicinfo['Title'], comicinfo['Writer'], comicinfo['Penciller'] = parse_filename(text, self.translator)
        else:
            comicinfo['Title'] = text

        if comicinfo.get('Writer') is None:
            tags = data.get("tags", [])
            self.fill_field(comicinfo, "Writer", tags, ["group", "artist"])
        if comicinfo.get('Penciller') is None:
            tags = data.get("tags", [])
            self.fill_field(comicinfo, "Penciller", tags, ["artist", "group"])
            
        # 提取汉化组信息, 汉化组一般会在 title 而不是 title_jpn 中出现
        translator = find_translator(html.unescape(data['title']))
        if translator: comicinfo['Translator'] = translator

        # 尝试为一些具有系列特征的标题提取系列名和集数
        series_name = None
        number = None
        
        # 检查是否有 multi-work series 标签
        series_keywords = ["multi-work series", "系列作品"]
        has_series_tag = False
        if comicinfo and comicinfo.get('Tags'):
            tags_list = [tag.strip().lower() for tag in comicinfo['Tags'].split(',')]
            has_series_tag = any(k.lower() in tags_list for k in series_keywords)
        
        # 检查配置
        prefer_openai = self.config.get('PREFER_OPENAI_SERIES', False)
        
        if prefer_openai and has_series_tag:
            # 策略1: OpenAI/aggressive 优先 (仅限有 multi-work series 标签)
            if logger: logger.info('检测到该作品为系列作品，优先使用 OpenAI 进行检测')
            series_name, number = self.get_series_for_multi_work_series(comicinfo['Title'], logger)
            
            # 失败时使用标准正则作为补救
            if not series_name:
                if logger: logger.info('OpenAI 模式检测失败，使用标准正则作为回退方案')
                series_name, number = self.extract_before_chapter(comicinfo['Title'], logger)
        else:
            # 策略2: 标准正则优先 (默认)
            series_name, number = self.extract_before_chapter(comicinfo['Title'], logger)
            
            # 标准正则失败且有 multi-work series 标签时，尝试 aggressive 模式
            if not series_name and has_series_tag:
                if logger: logger.info('未检测到章节信息，尝试为系列作品使用 OpenAI 进行检测')
                series_name, number = self.get_series_for_multi_work_series(comicinfo['Title'], logger)
        
        comicinfo['Series'] = series_name
        comicinfo['Number'] = number
        
        return comicinfo