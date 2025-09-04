# Hentai Assistant

## 安装与运行

### 方式一：本地运行

1. 克隆仓库
   ```bash
   git clone https://github.com/你的用户名/hentai-assistant.git
   cd hentai-assistant
   ```
2. 安装依赖
   ```
   pip install -r requirements.txt
   ```
3. 运行
   ```
   python src/main.py
   ```

### 方式二：Docker

```
 docker run -d -p 5001:5001 -v /home/yourname/hentai-assistant:/data ghcr.io/rosystain/hentai-assistant:latest
```

## 使用说明

首次使用前需要修改配置文件

### 修改配置文件

可直接前往 `http://<your-server>:<port>>/config`修改配置，默认 `<port>`为 `5001`

### 发送下载请求

可直接在浏览器请求 `http://<your-server>:<port>/api/download?url=<url>`, 将 `<url>`替换为你要下载的EH画廊链接。
也可以使用下列脚本发送请求。

- [Userscript](https://greasyfork.org/zh-CN/scripts/541108-hentai-assistant)
  - 在画廊边栏增加一个按钮用于推送下载请求。
- [iOS 快捷指令](https://www.icloud.com/shortcuts/27f2d38a7c334ff2824c3a63a53ec7e6)
  - 通过共享表单获取链接，并推送下载请求。
  - 使用前须编辑指令中的服务器信息

### 查看下载任务 (施工中)

访问 `http://<your-server>:<port>/download`

## 鸣谢

- 广告页检测：[hymbz/ComicReadScript](https://github.com/hymbz/ComicReadScript)
- 标签翻译数据库：[EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)
