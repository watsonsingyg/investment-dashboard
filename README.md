# 战投工作台

本项目是一个本地投资记录与动态看板工具。Excel 仍是唯一权威数据源，Flask 后端提供登录、周报生成、Excel 写入、动态看板 API、数据治理、导出和项目资料编辑。

## 启动

```bash
cd /Users/admin/Desktop/周报
pip install -r requirements.txt
bash start.sh
```

访问：`http://localhost:8766`

如果端口 `8766` 被占用，`start.sh` 会提示先处理占用进程，不会无差别杀掉其他服务。

桌面应用 `/Users/admin/Desktop/战投工作台.app` 也调用同一套 `start.sh` 启动逻辑：

- 已有工作台服务在运行：直接复用并打开页面。
- 已有服务启动时间早于本地代码更新时间：自动重启并加载新版页面。
- 端口被其他服务占用：提示占用进程，不会强制结束。
- 服务日志统一写入：`logs/server.log`。
- 查看运行状态：`bash start.sh --status`。
- 强制加载新版：`bash start.sh --restart --background --open`。

AI 生成模型可在 `.env` 里通过 `DEEPSEEK_MODEL` 配置，例如：

```bash
DEEPSEEK_MODEL=deepseek-v4-pro
```

## 数据结构

主数据源：`周报 database.xlsx`

- 第 1 列：项目编号
- 第 2 列：时间
- 第 3 列：项目
- 第 4 列：业务范畴
- 第 5 列：细分行业
- 第 6 列：负责人
- 第 7 列：项目状态
- 第 8 列：优先级
- 第 9 列：项目打分（1-5）
- 第 10 列起：周报动态，表头必须是 `YYYY/MM/DD-YYYY/MM/DD`

状态会统一归一到：`前期沟通`、`正式尽调`、`协议签署/交割`、`投后`。
项目打分展示为：`1 拉完了`、`2 NPC`、`3 人上人`、`4 顶级`、`5 夯爆了`。

## 备份、日志和影子库

- 每次写入 Excel 前，会在 `backups/` 下生成备份。
- 操作日志写入 `logs/operations.jsonl`。
- 字段级变更记录写入 SQLite：`pipeline_shadow.db` 的 `field_diffs` 表。
- SQLite 只是影子库，用于查询、导出和迁移预演；Excel 仍是权威数据源。

## 常用命令

```bash
python3 generate_dashboard.py
python3 check_app.py
```

`generate_dashboard.py` 会生成轻量 dashboard shell，并同步 SQLite。看板数据运行时通过 `/api/dashboard-data` 获取。

## 页面入口

- `/`：工作台入口，打开看板、生成器、数据治理。
- `/dashboard`：投资 Pipeline 动态看板。
- `/reporter`：周报生成器，支持本地草稿自动保存、最近周报复用和常用字段补全。
- `/governance`：项目健康检查，提示缺负责人、缺优先级、缺评分、缺状态、长期无更新、无任何周报、无本周更新、异常周次和疑似重复项目。
- `/status`：运行状态和服务日志，只读展示 PID、启动时间、模型、Excel、同步状态和日志尾部。

## 主要接口

- `GET /api/dashboard-data`：看板数据
- `GET /api/governance-data`：项目健康检查数据
- `POST /api/governance/issue-state`：确认、忽略或恢复健康检查问题，状态写入 `logs/governance_overrides.json`
- `GET /api/health`：无登录健康检查，用于启动脚本识别工作台服务
- `GET /api/system-status`：登录后查看运行状态、PID、模型、Excel 和同步信息
- `GET /api/server-log?lines=200`：登录后读取 `logs/server.log` 尾部内容
- `GET /api/field-options`：生成器和修正表单使用的常用字段选项
- `GET /api/projects/<project>`：项目资料
- `PATCH /api/projects/<project>`：编辑项目状态、优先级、评分、负责人、业务范畴、细分行业
- `GET /api/export/projects.csv`：导出项目表
- `GET /api/export/project/<project>.md`：导出单项目时间轴
- `GET /api/export/weekly.md?week=YYYY/MM/DD-YYYY/MM/DD`：导出周动态

## 注意事项

- 不要手动改 `pipeline_shadow.db`；需要修数据时改 Excel。
- 如果 Excel 表头不是标准日期区间，系统不会把它识别为周报列。
- 上传材料限制：单文件 10MB，总计 25MB。
