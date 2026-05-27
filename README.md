# Daily Article TTS / 早报电台

每日自动抓取微信公众号文章（猫笔刀、刘备教授），转为语音播报。

## 功能

- 每天自动抓取最新文章
- Edge TTS 语音合成（晓晓 voice）
- 网页在线播放
- 微信小程序推送（本地模式）

## 在线访问

**GitHub Pages**: https://wisdomseekerwang-png.github.io/daily-article-tts/

## 定时任务

- **GitHub Actions**: 每天 UTC 00:00 (北京时间 08:00) 自动运行
- **WorkBuddy 自动化**: 本地模式，8:00 抓取 + 9:00 播放

## 本地使用

```bash
pip install edge-tts httpx
python fetch_articles_tts.py              # 本地模式
python fetch_articles_tts.py --serverless # CI/CD 模式
```

## 项目结构

```
fetch_articles_tts.py  # 主脚本（抓取 + TTS）
build.py               # 构建脚本
web/                   # 网页播放器
  index.html
  css/style.css
  js/app.js
.github/workflows/     # GitHub Actions
```
