import re
import html
import langcodes

from openai_helper import OpenAIHelper
from providers import ehentai

def normalize_tilde(filename: str) -> str:
    filename = re.sub(r'([话話])(?!\s)', r'\1 ', filename)
    filename = re.sub(r'([~⁓～—_「-])', ' ', filename)
    return filename

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
        for pat in patterns:
            m = re.search(pat, filename, re.I)
            if m:
                return clean_name(m.group(1)).strip()
            
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

            # 检查返回是否有效且无错误
            if openai_result and not openai_result.get('error') and openai_result.get('series'):
                if logger: logger.info(f"识别结果为: {openai_result}")
                return openai_result.get('series')
        
        # 如果没有匹配任何章节模式 → 返回第一个空格前的内容
        is_aggressive_series_detection = self.config.get('AGGRESSIVE_SERIES_DETECTION', False)
        if is_aggressive_series_detection:
            filename = filename.strip()
            idx = filename.find(' ')
            if idx == -1:
                return  clean_name(filename).strip()
            return clean_name(filename[:idx]).strip()
        
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
        collectionlist = []
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
                    if tag_name in ehentai.male_only_taglist():
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
        if not collectionlist == []: comicinfo['SeriesGroup'] = ', '.join(collectionlist)
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

        # 尝试为一些具有系列特征的标题提取系列名
        comicinfo['Series'] = self.extract_before_chapter(comicinfo['Title'], logger)
        if not comicinfo.get('Series'):
            # 为自带 multi-work series 标签的作品作进一步分析
            series_keywords = ["multi-work series", "系列作品"]
            comicinfo['Series'] = None
            if comicinfo and comicinfo.get('Tags'):
                tags_list = [tag.strip().lower() for tag in comicinfo['Tags'].split(',')]
                matched = any(k.lower() in tags_list for k in series_keywords)
                if matched:
                    if logger: logger.info('即将为 Multi-work series 作品系列名进行识别')
                    comicinfo['Series'] = self.get_series_for_multi_work_series(comicinfo['Title'], logger)
        
        return comicinfo