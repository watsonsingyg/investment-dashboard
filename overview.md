# Pipeline 管理系统 · 第二轮改进报告

**日期**: 2026-05-27

## 🌐 当前可访问地址

| 地址 | 说明 |
|------|------|
| **`https://a27aeb6bb31d488ba37eb67a3ebdfcab.app.codebuddy.work`** | 🌍 **公开演示站**（CloudStudio 部署） |
| `http://localhost:8089/login` | 开发服务器（新版 Jinja2 模板） |
| `http://localhost:8766/login` | 旧版服务器（仍在运行） |

---

## ✅ 第二轮改进（本轮完成）

### 1. 🏗️ 模板组件化重构
> **之前**: 6 个模板各自写完整 navbar + DOCTYPE + head，改一个地方要改 6 个文件。
> **现在**: 全部模板通过 `{% extends "_base.html" %}` 继承共享布局。

- 创建 `reporter/templates/_base.html` — Jinja2 布局模板
  - 统一管理 DOCTYPE / meta / favicon / navbar / mobile menu / scripts
  - 通过 `nav_full` / `show_navbar` / `active_page` 等变量控制导航状态
- 全部 10 个模板转为 `{% block content %}` 格式，只保留页面独有内容
- pages.py / settings.py / admin.py 统一使用 `render_template()` 替代字符串替换
- **结果**: 模板代码减少 ~60%，新增页面只需写内容区块

### 2. 💀 骨架屏加载动画
- base.css 新增 shimmer 动画骨架样式
- dashboard.html / governance.html 在数据加载前展示骨架占位符
- 支持 `.w-16` / `.w-24` / `.w-32` / `.w-full` 等宽度工具类
- 深色模式自动适配

### 3. 📱 PWA 离线支持
- **`reporter/static/sw.js`** — Service Worker
  - Cache First: 静态资源（CSS/JS/字体）
  - Network First: API 请求（失败时回退缓存）
  - 离线时返回 JSON 503 或缓存内容
- **`reporter/static/manifest.json`** — 支持「添加到主屏幕」
  - theme_color: 琥珀色 #D97706
  - SVG 图标，自适应大小
- base.js 自动注册 Service Worker

### 4. 🛡️ 全局错误边界
- auth.js fetch 拦截器增强：
  - **30 秒请求超时**（AbortController），超时自动提示
  - **离线检测**：navigator.onLine 检查
  - **403 自动提示**「权限不足」
  - **5xx 自动提示**「服务器繁忙，请稍后重试」
  - refresh token 流程不变（401 自动刷新）

### 5. 🌍 CloudStudio 公开部署
- 生成自包含静态演示页面（含真实设计系统、指标数据、暗色模式）
- 部署到 CloudStudio，获得公开 HTTPS 访问链接

---

## 📂 新增文件汇总

| 文件 | 用途 |
|------|------|
| `reporter/templates/_base.html` | Jinja2 共享布局模板 |
| `reporter/static/base.js` | UI 工具 + SW 注册 |
| `reporter/static/toast.js` | Toast 通知 |
| `reporter/static/sw.js` | Service Worker（PWA） |
| `reporter/static/manifest.json` | PWA 应用清单 |
| `reporter/templates/404.html` | 自定义 404 页面 |
| `dist/index.html` | CloudStudio 部署用静态页面 |

---

## 🔧 剩余建议（低优先级）

1. **真实域名部署**: docker-compose 部署到云服务器 + Nginx 反向代理 + HTTPS
2. **无障碍增强**: 更多 ARIA 标签，键盘导航优化
3. **国际化**: 中英文切换支持
