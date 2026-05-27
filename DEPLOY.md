# 🚀 pipelio.onl 部署指南

> 方案 A：Netlify 管理域名 + Railway 运行应用

---

## 架构

```
pipelio.onl (域名)
    │
    ├── Netlify DNS ──→ CNAME 指向 Railway
    │
    └── Railway ──→ Docker 容器 (Flask + Python)
                        │
                        └── PostgreSQL (Railway 托管)
```

---

## 第一步：部署到 Railway

### 1.1 注册 Railway

访问 [railway.app](https://railway.app)，用 GitHub 账号登录。

### 1.2 创建项目

1. 点击 **New Project** → **Deploy from GitHub repo**
2. 选择 `pipeline-saas` 仓库（或你的仓库名）
3. Railway 会自动检测 `Dockerfile` 并开始构建

### 1.3 添加 PostgreSQL

1. 在项目页面，右键空白处 → **Add Service** → **Database** → **PostgreSQL**
2. Railway 会自动创建 PostgreSQL 实例，并将 `DATABASE_URL` 环境变量注入到你的应用

### 1.4 配置环境变量

在应用的 **Variables** 标签页中，添加以下变量：

| 变量 | 值 | 说明 |
|------|-----|------|
| `APP_DEBUG` | `false` | 关闭调试模式 |
| `FLASK_SECRET` | （生成的随机字符串） | Flask session 密钥 |
| `JWT_SECRET` | （生成的随机字符串） | JWT 签名密钥 |
| `PORTAL_PASSWORD` | （你的登录密码） | 登录密码 |
| `DEEPSEEK_API_KEY` | `sk-...` | AI 周报生成（可选） |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | AI 模型（可选） |

> 📌 `DATABASE_URL` 和 `PORT` 由 Railway 自动设置，**不要手动添加**。

**生成随机密钥**（在终端执行）：
```bash
python3 -c "import secrets; print('FLASK_SECRET:', secrets.token_hex(32)); print('JWT_SECRET:', secrets.token_hex(32))"
```

### 1.5 部署

Railway 在每次 Git push 时会自动重新部署。你也可以在控制台手动点击 **Deploy**。

构建完成后，你会看到一个 `xxxxx.up.railway.app` 的域名——这就是你的应用地址。

---

## 第二步：绑定自定义域名

### 2.1 在 Railway 添加域名

1. 进入 Railway 项目 → 你的应用 Service → **Settings** → **Domains**
2. 点击 **Generate Domain** 或 **Add Custom Domain**
3. 输入 `pipelio.onl`
4. Railway 会显示一个 CNAME 目标值，例如：
   ```
   CNAME pipelio.onl → xxxxx.up.railway.app
   ```

### 2.2 在 Netlify 配置 DNS

1. 登录 [Netlify](https://app.netlify.com) → 选择 pipelio.onl 站点
2. 进入 **Domain settings** → **DNS settings**
3. 如果域名 `pipelio.onl` 是通过 Netlify 购买的：
   - 进入 **Domain management** → 删除默认的 Netlify A 记录
   - 添加一条 **CNAME 记录**：
     - **Name**: `@`（或留空，表示根域名）
     - **Value**: `xxxxx.up.railway.app`（Railway 给的 CNAME 目标）
4. 如果是外部域名指向 Netlify DNS：
   - 在 Netlify DNS 面板中，修改或添加 CNAME 记录

### 2.3 等待 DNS 生效

DNS 变更可能需要 **几分钟到几小时** 全球生效。你可以用以下命令检查：
```bash
dig pipelio.onl CNAME
```

---

## 第三步：验证部署

```bash
# 健康检查
curl https://pipelio.onl/api/health

# 应该返回类似：
# {"app":"pipeline-saas","status":"ok",...}
```

在浏览器中访问：
- `https://pipelio.onl` — 登录页面
- `https://pipelio.onl/dashboard` — Pipeline 看板
- `https://pipelio.onl/api/health` — 健康检查

---

## 第四步：提交代码

将新增的文件提交到 GitHub，Railway 会自动部署：

```bash
git add Dockerfile .dockerignore docker-entrypoint.sh DEPLOY.md
git commit -m "chore: 云部署配置 (Dockerfile 修复 + Railway 部署指南)"
git push
```

---

## 常见问题

### Q: Railway 免费额度够用吗？
Railway 新用户有 $5 免费额度。月费约：
- 应用容器：$5/月起（512MB RAM）
- PostgreSQL：$1/月起（256MB RAM）

如果超过免费额度会自动扣费，也可以设置消费上限。

### Q: 如何查看日志？
Railway → 你的应用 → **Deployments** → 点击最近的部署 → **Build Logs** / **Deploy Logs**

### Q: 部署失败怎么办？
常见原因：
1. PostgreSQL 未就绪 → 入口脚本会自动重试，等待 1-2 分钟
2. 缺少环境变量 → 检查 `FLASK_SECRET` 和 `JWT_SECRET` 是否已设置
3. 构建超时 → Railway 首次构建可能需要 5-10 分钟

### Q: 如何更新应用？
直接 `git push` 到 GitHub，Railway 会自动检测并重新部署。

### Q: Netlify 上的旧文件怎么办？
部署成功后，可以删除 Netlify 站点上的静态文件（或保留不管，DNS 指向 Railway 后不再生效）。
