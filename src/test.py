from providers  import ehentai
from config import config_parser

eh = ehentai.EHentaiTools(cookie=config_parser['ehentai']['cookie'])
response = eh.get_session()

print(response.text)