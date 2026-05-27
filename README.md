# 投资 Pipeline 管理系统

面向投资机构的项目 Pipeline 管理工具。提供 AI 辅助周报生成、动态看板、数据治理等功能。

Excel 仍是默认数据源，Flask 后端提供 Web 界面和 REST API。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制模板并填入实际值）
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY、PORTAL_PASSWORD 等

# 3. 启动服务
bash start.sh

# 4. 打开浏览器
open http://localhost:8766
```

> 所有配置项说明见 `.env.example`，无硬编码路径。

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `PORT` | `8766` | 服务端口 |
| `APP_HOST` | `127.0.0.1` | 监听地址 |
| `PORTAL_PASSWORD` | — | 登录密码（必须设置） |
| `FLASK_SECRET` | 随机生成 | Session 密钥 |
| `DEEPSEEK_API_KEY` | — | AI 生成 API Key |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | 使用的模型 |
| `TAVILY_API_KEY` | — | Tavily 搜索 API（可选） |
| `ANTHROPIC_API_KEY` | — | Claude 摘要 API（可选） |
| `SKILL_ROOT` | — | AI 分析框架 Skill 文件目录（可选） |
| `REPORT_DIR` | 项目根目录 | 数据文件所在目录 |
| `MAX_BACKUPS` | `30` | Excel 备份保留数 |
| `STALE_WEEKS_THRESHOLD` | `8` | 长期无更新阈值（周） |

## 项目结构

```
周报/
├── config.py                  # 集中配置管理
├── .env.example               # 环境变量模板
├── requirements.txt           # Python 依赖
├── start.sh                   # 启动脚本
├── generate_dashboard.py      # 看板静态生成
├── check_app.py               # 健康检查测试
├── 周报 database.xlsx         # 主数据文件
├── dashboard.html             # 静态看板（自动生成）
├── backups/                   # Excel 备份
├── logs/                      # 操作日志 + 治理记录
├── pipeline_shadow.db         # SQLite 影子库
└── reporter/                  # Flask 应用
    ├── app.py                 # 主入口
    ├── logger.py              # 结构化日志
    ├── ai_service.py          # AI 生成 + 搜索
    ├── dashboard_api.py       # 看板数据聚合
    ├── dashboard_data.py      # Excel 解析
    ├── dashboard_render.py    # 看板 HTML 渲染
    ├── excel_store.py         # Excel 读写 + 备份
    ├── export_service.py      # CSV/MD 导出
    ├── governance.py          # 数据健康检查
    ├── operation_log.py       # 操作日志
    ├── shadow_store.py        # SQLite 同步
    ├── statuses.py            # 状态词汇表
    ├── summary_cache.py       # 摘要缓存
    ├── validation.py          # 输入校验
    ├── templates/             # HTML 模板
    └── static/                # JS/CSS
```

## 页面入口

| 路由 | 功能 |
|------|------|
| `/` | 工作台门户 |
| `/dashboard` | Pipeline 动态看板（漏斗图、评分分布、行业分类） |
| `/reporter` | AI 周报生成器（流式生成、文件上传、草稿保存） |
| `/governance` | 数据治理（9 类问题检测、批量修正） |
| `/status` | 运行状态（PID、启动时间、日志查看） |

## API 接口

### 健康 & 系统
- `GET /api/health` — 无登录健康检查
- `GET /api/system-status` — 运行状态（需登录）
- `GET /api/server-log?lines=200` — 服务日志（需登录）

### 项目
- `GET /api/projects` — 项目列表
- `GET /api/projects/<project>` — 项目详情
- `PATCH /api/projects/<project>` — 编辑项目字段
- `GET /api/field-options` — 字段可选值

### 看板
- `GET /api/dashboard-data` — 看板聚合数据

### AI 生成
- `POST /api/generate` — SSE 流式生成周报
- `POST /api/push` — 推送周报至 Excel

### 治理
- `GET /api/governance-data` — 健康检查报告
- `POST /api/governance/issue-state` — 更新问题状态

### 审计
- `GET /api/audit/recent` — 最近变更
- `GET /api/audit/project/<project>` — 项目变更记录

### 导出
- `GET /api/export/projects.csv` — 导出项目 CSV
- `GET /api/export/project/<project>.md` — 导出项目 Markdown
- `GET /api/export/weekly.md?week=...` — 导出周报 Markdown

## 数据结构

主数据源：Excel 文件（`.xlsx`）

| 列 | 字段 | 说明 |
|----|------|------|
| 3 | 项目名称 | 唯一标识 |
| 4 | 业务范畴 | 投资领域 |
| 5 | 细分行业 | 具体行业 |
| 6 | 负责人 | 跟进人员 |
| 7 | 项目状态 | 前期沟通/正式尽调/协议签署交割/投后 |
| 8 | 优先级 | 高/中/低 |
| 9 | 项目打分 | 1-5 |
| 10+ | 周报动态 | 表头格式：`YYYY/MM/DD-YYYY/MM/DD` |

## 注意事项

- Excel 是权威数据源，SQLite 仅作查询和迁移预演
- 每次写操作自动备份到 `backups/`，保留最近 30 份
- 上传材料限制：总大小 25MB
- 不要手动修改 `pipeline_shadow.db`
