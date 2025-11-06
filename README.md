# Hentai Assistant

> ⚠️ **Work In Progress** - 项目仍在早期开发中，部分功能可能不稳定

一个 E-Hentai/ExHentai 自动化下载与管理工具，同时兼容 NHentai、Hitomi、HDoujin 等其他画廊站点。

[![Docker](https://img.shields.io/badge/docker-available-blue.svg)](https://github.com/rosystain/hentai-assistant/pkgs/container/hentai-assistant)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)


## 核心特性

-  **E-Hentai 优化** - 专为 E-Hentai/ExHentai 设计，完整支持 Archive、Torrent 下载
- **多站点兼容** - 同时支持 NHentai、Hitomi、HDoujin 作为补充数据源
- **智能回退** - 遇到失效画廊时自动在其他可用站点尝试找到关联内容
- **收藏夹同步** - 自动同步 E-Hentai 收藏夹，支持增量更新和自动下载
- **元数据管理** - 生成标准 ComicInfo.xml，支持基于 [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database) 的标签翻译和 Jinja2 公式的自定义模板
- **Komga 集成** - 对接 Komga 媒体库，支持自动扫描媒体库，支持以 WebHook 通知形式转发 SSE 事件
- **通知系统** - 任务完成、错误告警，支持多种通知渠道
- **Web 管理界面** - 现代化的响应式界面，实时任务监控

## 快速开始

### Docker 部署（推荐）

```bash
docker run -d \
  -p 5001:5001 \
  -v $(pwd)/data:/app/data \
  -e PUID=$(id -u) \
  -e PGID=$(id -g) \
  --name hentai-assistant \
  ghcr.io/rosystain/hentai-assistant:latest
```

访问管理界面: `http://localhost:5001`

### 本地开发运行

```bash
# 克隆仓库
git clone https://github.com/your-username/hentai-assistant.git
cd hentai-assistant

# 安装后端依赖
pip install -r requirements.txt

# 安装前端依赖（可选，仅开发模式需要）
cd webui && npm install && cd ..

# 终端1：启动应用
python src/main.py

# 终端2: 启动前端
cd webui
npm run dev
```

## 配置

配置文件位于 `data/config.yaml`，首次运行时自动生成。

**所有配置项都可以通过 Web 界面进行修改：** `http://localhost:5001/config`

详细的配置说明请参考 **[配置指南](wiki/Configuration.md)**。

## 使用示例

### API 下载

```bash
# 从 E-Hentai 下载
curl "http://localhost:5001/api/download?url=https://exhentai.org/g/123456/abcdef/"

# 下载并添加到收藏夹
curl "http://localhost:5001/api/download?url=https://exhentai.org/g/123456/abcdef/&fav=0"

# 从其他站点下载（NHentai/Hitomi/HDoujin）
curl "http://localhost:5001/api/download?url=https://nhentai.net/g/123456/"
```

## 鸣谢

- 广告页检测: [hymbz/ComicReadScript](https://github.com/hymbz/ComicReadScript)
- 标签翻译数据库: [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)


## 免责声明

本项目仅供个人学习和研究使用。使用本工具时请：

- 遵守所在地区的法律法规
- 尊重内容创作者的版权
- 遵守目标网站的服务条款和使用限制
- 合理控制下载频率，避免对服务器造成压力

使用者需自行承担使用本工具可能产生的一切风险和责任。