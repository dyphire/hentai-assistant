import openai
import time

class OpenAIHelper:
    def __init__(self, api_key, base_url, model, logger=None):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.prompt = """我会给你本书的标题，这本书是一个系列故事中的一集，根据标题推断出这个系列的名字(series)，以及这一集所匹配的序号(number)，按照以下格式我 series:value\nnumber:value 返回给我，如果无法推断出系列名或者序号，请返回 None 作为值。"""
        self.logger = logger

    def query(self, title, retries=3, timeout=15):
        if not isinstance(title, str):
            return {"error": "Input title must be a string."}
        
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
                if self.logger: self.logger.info(f"OpenAI response: {response.choices[0].message.content}")
                return self.parse_response(response.choices[0].message)
            except Exception as e:
                last_exception = e
                if self.logger: self.logger.warning(f"OpenAI query attempt {attempt + 1} failed: {e}")
                time.sleep(1)  # Wait 1 second before retrying
        
        if self.logger: self.logger.error(f"OpenAI query failed after {retries} retries: {last_exception}")
        return {"error": str(last_exception)}

    def parse_response(self, response):
        content = response.content
        data = {}
        for line in content.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1) # 只分割一次
                key = key.strip()
                value = value.strip()
                # 简单类型转换
                if value.isdigit():
                    data[key] = int(value)
                else:
                    data[key] = value
        return data