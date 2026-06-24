# Contabo VPS 部署指南（Ubuntu + Cloudflare）

适用于：在 **Contabo VPS（Ubuntu 22.04，US East）** 上完整部署 fast-doc（FastAPI + PostgreSQL + pgvector），通过 **Cloudflare Tunnel** 对外暴露 API，无需开放 80/443 入站端口。

流量路径：客户端 → Cloudflare Edge（WAF + TLS）→ Tunnel → VPS `127.0.0.1:8000`

---

## 1. 前提条件

| 项目 | 说明 |
|------|------|
| Contabo VPS | Ubuntu 22.04，US East，4 vCPU / 8 GB RAM / 150 GB SSD |
| Cloudflare 账号 | 已在 Cloudflare Registrar 购买域名，DNS 由 Cloudflare 托管 |
| 本地机器 | 可 SSH 连接 VPS |

---

## 2. 初始服务器配置

### 2.1 SSH 登录与创建非 root 用户

```bash
# 本地：用 Contabo 提供的 root 密码登录
ssh root@<VPS_IP>

# 创建部署用户
adduser deploy
usermod -aG sudo deploy

# 将本地 SSH 公钥复制到新用户
# 本地执行：
ssh-copy-id deploy@<VPS_IP>
```

后续所有操作均以 `deploy` 用户执行。

### 2.2 基础防火墙（仅开 SSH）

```bash
sudo ufw allow 22/tcp
sudo ufw enable
sudo ufw status
```

Cloudflare Tunnel 使用出站连接，**无需开放 80/443**。

### 2.3 更新系统

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

---

## 3. 安装 PostgreSQL 15 + pgvector

```bash
# 安装 PostgreSQL 15
sudo apt-get install -y postgresql-15 postgresql-client-15

# 安装 pgvector 扩展
sudo apt-get install -y postgresql-15-pgvector

# 启动并设置开机自启
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### 3.1 创建数据库与用户

```bash
sudo -u postgres psql <<'SQL'
CREATE USER fastdoc WITH PASSWORD 'your_strong_password';
CREATE DATABASE fastdoc OWNER fastdoc;
\c fastdoc
CREATE EXTENSION IF NOT EXISTS vector;
\q
SQL
```

### 3.2 确认 pgvector 已启用

```bash
sudo -u postgres psql -d fastdoc -c "\dx vector"
```

输出包含 `vector` 即表示成功。

PostgreSQL 仅监听 `127.0.0.1`，无需对外暴露。

---

## 4. 部署 FastAPI 应用

### 4.1 安装 uv（Python 包管理）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### 4.2 克隆代码并安装依赖

```bash
git clone <your-repo-url> /home/deploy/fast-doc
cd /home/deploy/fast-doc
uv sync
```

### 4.3 配置环境变量

```bash
cp .env.example .env   # 如无则新建
nano .env
```

最少需要设置：

```env
DATABASE_URL=postgresql+asyncpg://fastdoc:your_strong_password@127.0.0.1:5432/fastdoc
SECRET_KEY=<随机长字符串>
```

### 4.4 运行数据库迁移

```bash
uv run alembic upgrade head
```

### 4.5 验证本地服务启动

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
# 新终端测试：
curl http://127.0.0.1:8000/health
# 应返回：{"status":"ok"}
```

### 4.6 注册为 systemd 服务

```bash
sudo nano /etc/systemd/system/fastdoc.service
```

写入：

```ini
[Unit]
Description=FastDoc API
After=network.target postgresql.service

[Service]
User=deploy
WorkingDirectory=/home/deploy/fast-doc
EnvironmentFile=/home/deploy/fast-doc/.env
ExecStart=/home/deploy/.local/bin/uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable fastdoc
sudo systemctl start fastdoc
sudo systemctl status fastdoc
```

---

## 5. Cloudflare Tunnel 配置

### 5.1 在 Cloudflare Dashboard 创建 Tunnel

1. 进入 **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel**
2. 名称填 `fast-doc`，类型选 **Cloudflared**，保存
3. 选择 **Debian**（兼容 Ubuntu），复制页面上的安装命令（含 token）

### 5.2 在 VPS 安装 cloudflared

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt-get update && sudo apt-get install -y cloudflared

# 注册为系统服务（粘贴 Dashboard 给出的完整命令）
sudo cloudflared service install <token>

sudo systemctl status cloudflared
```

### 5.3 配置 Public Hostname

回到 Tunnel 配置页 → **Public Hostname** → **Add a public hostname**：

| 字段 | 填写 |
|------|------|
| Subdomain | `api` |
| Domain | `yourdomain.com` |
| Service Type | `HTTP` |
| URL | `http://127.0.0.1:8000` |

保存后 Cloudflare 自动添加 DNS CNAME 记录，无需手动操作。

### 5.4 验证

```bash
curl -sS https://api.yourdomain.com/health
# 应返回：{"status":"ok"}
```

---

## 6. Cloudflare Email Service 配置

Cloudflare Email Service（2026 公测）支持完整收发，自动配置 SPF/DKIM/DMARC。

### 6.1 收件（Email Routing）

1. Cloudflare Dashboard → **Email** → **Email Routing** → 启用
2. 添加自定义地址：`support@yourdomain.com` → 转发到你的 Gmail
3. DNS 记录自动添加

### 6.2 发件（Email Service API）

1. Dashboard → **Email** → **Email Service** → 添加发件域名 `yourdomain.com`
2. 生成 API Token（权限：Email Service: Send）
3. 在 `.env` 中添加：

```env
CF_ACCOUNT_ID=<你的 Account ID>
CF_EMAIL_API_TOKEN=<API Token>
EMAIL_FROM=noreply@yourdomain.com
```

### 6.3 FastAPI 发件示例

```python
import httpx
from app.core.config import settings

async def send_email(to: str, subject: str, html: str) -> None:
    async with httpx.AsyncClient() as client:
        client.post(
            f"https://api.cloudflare.com/client/v4/accounts/{settings.CF_ACCOUNT_ID}/email/send",
            headers={"Authorization": f"Bearer {settings.CF_EMAIL_API_TOKEN}"},
            json={
                "from": settings.EMAIL_FROM,
                "to": [to],
                "subject": subject,
                "html": html,
            },
        )
```

免费额度：**3,000 封/月**，早期 SaaS 完全够用。

---

## 7. 安全加固（可选但建议）

### Zero Trust Access（保护管理接口）

在 Cloudflare Dashboard → **Zero Trust** → **Access** → **Applications**：
- 添加应用，路径 `api.yourdomain.com/v1/admin/*`
- 策略：仅允许你的邮箱登录
- 零代码，15 分钟配完

### Cloudflare WAF Rate Limiting

Dashboard → **Security** → **WAF** → **Rate limiting rules**：
- 路径 `/v1/auth/token`，限制 10 次/分钟/IP
- 防止暴力破解 JWT

---

## 8. 日常运维

```bash
# 查看 API 日志
sudo journalctl -u fastdoc -f

# 查看 Tunnel 日志
sudo journalctl -u cloudflared -f

# 更新代码
cd /home/deploy/fast-doc
git pull
uv sync
uv run alembic upgrade head
sudo systemctl restart fastdoc

# 升级 cloudflared
sudo apt-get install --only-upgrade cloudflared
```

---

## 9. 常见问题

| 现象 | 排查 |
|------|------|
| `{"status":"ok"}` 无法访问 | 先 `curl http://127.0.0.1:8000/health` 确认本地正常，再查 Tunnel 状态 |
| Tunnel 显示 inactive | `sudo journalctl -u cloudflared` 查 token 是否有效 |
| 数据库连接失败 | 确认 `.env` 中 `DATABASE_URL` 用户名密码与建库时一致 |
| pgvector 不可用 | `sudo -u postgres psql -d fastdoc -c "CREATE EXTENSION vector;"` |
| 发件失败 | 检查 `CF_ACCOUNT_ID` 和 `CF_EMAIL_API_TOKEN` 是否正确 |

---

## 10. 参考链接

- [Cloudflare Tunnel 文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Cloudflare Email Service 文档](https://developers.cloudflare.com/email-service/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [uv 文档](https://docs.astral.sh/uv/)
