# 配置指南

完整的配置文件说明，涵盖所有可用选项。

## 配置文件位置

配置文件位于 `data/config.yaml`，使用 YAML 格式。首次运行时会自动创建默认配置。

## 完整配置模板

```yaml
general:
  port: 5001
  keep_torrents: false
  keep_original_file: false
  prefer_japanese_title: true
  move_path: ""

advanced:
  tags_translation: false
  remove_ads: false
  aggressive_series_detection: false
  openai_series_detection: false
  prefer_openai_series: false

ehentai:
  ipb_member_id: ""
  ipb_pass_hash: ""
  favorite_sync: false
  favorite_sync_interval: "6h"
  favcat_whitelist: []
  initial_scan_pages: 1
  auto_download_favorites: false
  hath_check_enabled: false
  hath_check_interval: "30m"

nhentai:
  cookie: ""

hdoujin:
  session_token: ""
  refresh_token: ""
  clearance_token: ""
  user_agent: ""

aria2:
  enable: false
  server: "http://localhost:6800/jsonrpc"
  token: ""
  download_dir: ""
  mapped_dir: ""

komga:
  enable: false
  server: ""
  username: ""
  password: ""
  library_id: ""

notification: {}

openai:
  api_key: ""
  base_url: ""
  model: ""

comicinfo:
  title: "{{title}}"
  writer: "{{writer}}"
  penciller: "{{penciller}}"
  translator: "{{translator}}"
  tags: "{{tags}}"
  web: "{{web}}"
  agerating: "{{agerating}}"
  manga: "{{manga}}"
  genre: "{{genre}}"
  languageiso: "{{languageiso}}"
  alternateseries: "{{series}}"
  alternatenumber: "{{number}}"
```

## 配置项详解

### General (通用设置)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `port` | int | `5001` | Web 服务监听端口 |
| `keep_torrents` | bool | `false` | 保留下载的种子文件 |
| `keep_original_file` | bool | `false` | 保留转换前的原始文件 |
| `prefer_japanese_title` | bool | `true` | 优先使用日文标题 |
| `move_path` | string | `""` | 文件移动路径模板，留空则不移动 |

**move_path 模板变量:**

- `{{filename}}` - 原始文件名
- `{{author}}` - 作者（默认使用 Penciller, 缺失时使用 Writer）
- `{{writer}}` - 作者 / 社团名
- `{{penciller}}` - 画师名
- `{{series}}` - 系列名
- `{{title}}` - 标题

**示例:**

```yaml
# 按作者和系列分类
move_path: "/mnt/library/{{author}}/{{series}}/{{filename}}"

# 仅按作者分类
move_path: "/mnt/library/{{author}}/{{filename}}"

# 自定义文件名格式
move_path: "/mnt/library/[{{writer}}] {{title}}.cbz"
```

### Advanced (高级设置)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `tags_translation` | bool | `false` | 启用 E-Hentai 标签中英翻译 |
| `remove_ads` | bool | `false` | 自动检测并移除广告页 |
| `aggressive_series_detection` | bool | `false` | 使用更激进的系列名检测规则（可能不准确） |
| `openai_series_detection` | bool | `false` | 使用 OpenAI 识别系列名和序号（`aggressive_series_detection` 的替代，启用 OpenAI 模块）|
| `prefer_openai_series` | bool | `false` | 优先使用 OpenAI 结果而非正则 |

### E-Hentai 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `ipb_member_id` | string | `''` |E-Hentai Cookie 中获取 |
| `ipb_pass_hash` | string | `''` | E-Hentai Cookie 中获取 |
| `favorite_sync` | bool | `false`| 启用收藏夹自动同步 |
| `favorite_sync_interval` | string | `6h`| 收藏夹同步间隔（支持 `m`/`h`/`d` 单位，如 `30m`、`6h`、`1d`） |
| `favcat_whitelist` | list | `[]`| 要同步的收藏夹编号列表（0-9），空表示全部 |
| `initial_scan_pages` | int | `1`| 首次扫描页数，0 表示全量扫描|
| `auto_download_favorites` | bool | `false`| 自动下载本地收藏夹中缺失的项目 |
| `hath_check_enabled` | bool | `false`| 启用 H@H 客户端状态监控 |
| `hath_check_interval` | string | `30m`| H@H 状态检查间隔（支持 `m`/`h`/`d` 单位，最小 5 分钟） |

**时间间隔格式说明:**

时间间隔支持以下单位格式：
- **分钟**: `30m`, `15min`, `45mins`, `60minutes`
- **小时**: `6h`, `12hr`, `24hrs`, `2hours`
- **天**: `1d`, `7day`, `30days`

**H@H 监控功能:**

启用后会定期检查你的 Hentai@Home 客户端状态，并在状态变化时发送通知：
- 客户端离线通知
- 客户端恢复在线通知
- 其他状态变化通知

**API 端点:**
- `GET /api/ehentai/hath/status` - 获取所有客户端状态
- `GET /api/ehentai/hath/check` - 手动触发检查并返回最新状态


### NHentai 配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `cookie` | string | NHentai Cookie 字符串（可选） |

### HDoujin 配置

HDoujin 需要 Cloudflare 绕过 token，建议通过 Web 界面获取。

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `session_token` | string | 会话 Token |
| `refresh_token` | string | 用于刷新的 Token |
| `clearance_token` | string | Cloudflare Clearance Token |
| `user_agent` | string | 获取 Token 时使用的浏览器 User-Agent |

### Aria2 配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `enable` | bool | 启用 Aria2 RPC |
| `server` | string | Aria2 RPC 服务器地址 |
| `token` | string | RPC 密钥（如果设置了的话） |
| `download_dir` | string | Aria2 下载目录（容器内路径） |
| `mapped_dir` | string | 映射到主机的实际路径 |

**Docker 环境配置示例:**

```yaml
aria2:
  enable: true
  server: "http://aria2:6800/jsonrpc"
  token: "your_secret_token"
  download_dir: "/downloads"
  mapped_dir: "/mnt/downloads"  # 主机上的实际路径
```

### Komga 配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `enable` | bool | 启用 Komga 集成 |
| `server` | string | Komga 服务器地址 |
| `username` | string | Komga 用户名 |
| `password` | string | Komga 密码 |
| `library_id` | string | 目标媒体库 ID |

**获取 Library ID:**

1. 登录 Komga Web 界面
2. 进入目标媒体库
3. 查看 URL，格式为 `http://server/libraries/{library_id}`
4. 复制 `library_id` 部分

### OpenAI 配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `api_key` | string | OpenAI API Key |
| `base_url` | string | API 端点（支持兼容接口） |
| `model` | string | 使用的模型名称 |

**兼容接口示例:**

```yaml
openai:
  api_key: "sk-..."
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o-mini"

# 或使用兼容的第三方接口
openai:
  api_key: "your-key"
  base_url: "https://api.groq.com/openai/v1"
  model: "llama3-70b"
```

### 通知配置

通知系统支持 Apprise 和 Webhook 两种方式，可配置多个通知器。

```yaml
notification:
  telegram_bot:
    enable: true
    name: "Telegram"
    type: "apprise"
    url: "tgram://bot_token/chat_id"
    events:
      - "task.complete"
      - "task.error"
  
  discord_webhook:
    enable: true
    name: "Discord"
    type: "apprise"
    url: "discord://webhook_id/webhook_token"
    events:
      - "task.complete"
      - "komga.new"
  
  custom_webhook:
    enable: true
    name: "自定义 Webhook"
    type: "webhook"
    url: "https://your-server.com/webhook"
    events:
      - "task.start"
      - "task.complete"
      - "task.error"
```

**支持的事件:**

- `task.start` - 任务开始
- `task.complete` - 任务完成
- `task.error` - 任务失败
- `komga.new` - Komga 新书入库
- `komga.delete` - Komga 书籍被删除
- `hath.offline` - H@H 客户端离线
- `hath.online` - H@H 客户端恢复在线
- `hath.status_change` - H@H 客户端状态变化

详细配置请参考 [通知配置文档](Notifications.md)。

### ComicInfo 模板

使用 Jinja2 模板语法自定义元数据字段。

**可用变量:**

| 变量 | 说明 |
|------|------|
| `{{filename}}` | 文件名 |
| `{{title}}` | 清理后的标题 |
| `{{originaltitle}}` | 原始标题 |
| `{{writer}}` | 作者/社团 |
| `{{penciller}}` | 画师 |
| `{{translator}}` | 汉化组 |
| `{{genre}}` | 类型 |
| `{{category}}` | E-Hentai 分类 |
| `{{tags}}` | 标签列表 |
| `{{web}}` | 画廊 URL |
| `{{agerating}}` | 年龄分级 |
| `{{manga}}` | 翻页顺序 |
| `{{languageiso}}` | 语言 ISO 代码 |
| `{{series}}` | 系列名 |
| `{{number}}` | 系列序号 |

**Jinja2 语法示例:**

```yaml
comicinfo:
  # 标题后添加汉化组
  title: "{{originaltitle}}{% if translator %} [{{translator}}]{% endif %}"
  
  # 流派后添加分类
  genre: "{{genre}}{% if category %}, {{category}}{% endif %}"
  
  # 合并作者和画师字段
  writer: "{% if writer and penciller and writer != penciller %}{{writer}}, {{penciller}}{% elif writer %}{{writer}}{% elif penciller %}{{penciller}}{% endif %}"
```
模板中也可以加入一些其他字段（如 Kavita 的 `<LocalizedSeries>`）, 他们会一起写入最终的 ComicInfo.xml 中, 但最好使用严格的大小写。

**自定义字段示例:**

```yaml
  title: {{title}}
  LocalizedSeries: {{originaltitle}}
```

## 配置验证

修改配置后，可通过以下方式验证：

1. **重启应用** - 配置会在启动时加载和验证
2. **查看日志** - 检查 `data/app.log` 中的错误信息
3. **Web 界面** - 访问配置页面查看服务状态

## 配置文件迁移

如果你有旧版本的 INI 配置文件，应用会在启动时自动迁移到 YAML 格式。

---

[返回首页](../README.md)