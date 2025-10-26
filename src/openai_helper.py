import openai
import time
import json

class OpenAIHelper:
    def __init__(self, api_key, base_url, model, logger=None):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.prompt = """分析给定的书籍标题,以 JSON 格式返回系列名和集数。

规则:
- series: 系列名称(字符串)。无法推断时使用书名本身并去除无关文本
- number: 集数序号(数字或null)。可以是整数(如3)或小数(如2.5)。无法推断时返回null

仅返回 JSON,不要其他内容。

示例:
输入: "魔法少女小圆 第3话"
输出: {"series": "魔法少女小圆", "number": 3}

输入: "系列名 Vol.2.5"
输出: {"series": "系列名", "number": 2.5}

输入: "エルフの母と孕むまで 【ハード版】+ アフターストーリー"
输出: {"series": "エルフの母と孕むまで", "number": null}"""
        self.logger = logger

    def query(self, title, retries=3, timeout=15):
        if not isinstance(title, str):
            if self.logger: self.logger.error("Input title must be a string")
            return None
        
        last_exception = None
        for attempt in range(retries):
            try:
                if self.logger: self.logger.info(f"Querying OpenAI for title: '{title}' (Attempt {attempt + 1}/{retries})")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.prompt},
                        {"role": "user", "content": f"title:{title}"}
                    ],
                    timeout=timeout
                )
                return self.parse_response(response.choices[0].message)
            except Exception as e:
                last_exception = e
                if self.logger: self.logger.warning(f"OpenAI query attempt {attempt + 1} failed: {e}")
                time.sleep(1)  # Wait 1 second before retrying
        
        if self.logger: self.logger.error(f"OpenAI query failed after {retries} retries: {last_exception}")
        return None

    def parse_response(self, response):
        content = response.content.strip()
        
        # 检查空响应，抛出异常以触发重试
        if not content:
            raise ValueError("Received empty response from OpenAI")
        
        # 尝试提取 JSON (处理可能被代码块包裹的情况)
        json_content = content
        
        # 如果响应被 markdown 代码块包裹,提取其中的 JSON
        if content.startswith('```'):
            lines = content.split('\n')
            # 移除第一行的 ```json 或 ```
            if lines[0].strip() in ['```json', '```']:
                lines = lines[1:]
            # 移除最后一行的 ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            json_content = '\n'.join(lines).strip()
        
        # 尝试查找 JSON 对象 (以 { 开始)
        json_start = json_content.find('{')
        json_end = json_content.rfind('}')
        
        if json_start != -1 and json_end != -1 and json_end > json_start:
            json_content = json_content[json_start:json_end + 1]
        
        try:
            # 尝试解析 JSON 格式
            data = json.loads(json_content)
            
            # 将 number 字段转换为字符串形式(如果存在且不为 None)
            if 'number' in data and data['number'] is not None:
                data['number'] = str(data['number'])
            
            return data
        except json.JSONDecodeError as e:
            # 如果 JSON 解析失败，抛出异常以触发重试
            raise ValueError(f"Failed to parse JSON response. Original: '{content}', Extracted: '{json_content}', Error: {e}")