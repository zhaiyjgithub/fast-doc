# Ubuntu 上使用 Cloudflare Tunnel 暴露本机 API（仅开放 SSH 入站场景）

适用于：**主机入站只允许 22（SSH）**，但需要让公网（例如部署在 Vercel 上的前端）通过 **HTTPS** 访问本机上的 **FastAPI**（或 Nginx 反代后的 upstream）。流量路径为：浏览器 → Cloudflare 边缘 → **出站隧道**（`cloudflared`）→ `127.0.0.1` 上的服务。

**前提**：本机可以访问外网 **HTTPS 出站**（默认放行 `443` 即可）；无需在本机防火墙开放 `80/443` 入站。

---

## 1. 前提条件

| 项目 | 说明 |
|------|------|
| Cloudflare 账号 | 免费即可 |
| 域名 | 已添加到 Cloudflare，并使用 Cloudflare **DNS（Nameserver）** |
| 本机服务 | API 监听 `127.0.0.1:8000`（或下文你实际使用的端口） |
| Ubuntu | 本文以常见 x86_64 为例；ARM 请从 [GitHub Releases](https://github.com/cloudflare/cloudflared/releases) 选对应包 |

---

## 2. 在 Cloudflare 控制台创建 Tunnel

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)，进入 **Zero Trust**（若首次使用，按提示选择免费套餐并完成初始化）。
2. 左侧 **Networks** → **Tunnels** → **Create a tunnel**。
3. 名称自定（例如 `home-api`），类型选 **Cloudflared**，**Save tunnel**。
4. 在 **Install and run a connector** 页面选择 **Debian**（与 Ubuntu 兼容），复制页面上的安装命令；其中会包含一条 **`cloudflared service install <很长一串 token>`** —— **不要泄露该 token**，它等同于接入你内网的钥匙。
5. 先**不要关页面**，后面还要配置 **Public Hostname**。

---

## 3. 在 Ubuntu 上安装 `cloudflared`

### 方式 A：官方 APT 源（推荐）

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt-get update && sudo apt-get install -y cloudflared
```

### 方式 B：直接下载 deb

到 [cloudflared Releases](https://github.com/cloudflare/cloudflared/releases) 下载适合 Ubuntu 的 `.deb`，然后：

```bash
sudo dpkg -i cloudflared-linux-amd64.deb
```

验证版本：

```bash
cloudflared --version
```

---

## 4. 将 Tunnel 注册为系统服务（使用控制台给出的 token）

在控制台复制的命令类似：

```bash
sudo cloudflared service install eyJhIjo...
```

执行后，`cloudflared` 会作为 **systemd** 服务安装并启动，开机自启。

常用命令：

```bash
sudo systemctl status cloudflared
sudo systemctl restart cloudflared
sudo journalctl -u cloudflared -f
```

若服务未运行，先看日志里是否提示 token 无效、网络被拒等。

---

## 5. 配置 Public Hostname（把域名指到本机端口）

回到 Zero Trust 里该 Tunnel 的配置页：

1. 打开 **Public Hostname**（或 **Configured routes**）→ **Add a public hostname**。
2. **Subdomain**：例如 `api`；**Domain**：选你的根域（如 `example.com`），完整即为 `api.example.com`。
3. **Service**：
   - **Type**：`HTTP`
   - **URL**：`http://127.0.0.1:8000`（与 FastAPI / uvicorn 实际监听一致；若前面有 Nginx 反代，则写 `http://127.0.0.1:80` 等）
4. 保存。Cloudflare 会自动写入（或提示你确认）该子域的 **DNS**；因域名已在 Cloudflare，一般无需再到 DNS 面板手动加 A 记录到家庭公网 IP（Tunnel 不依赖你公网入站端口）。

等待数十秒至数分钟，用本机或外网执行：

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://api.example.com/health
```

（把路径换成你 API 真实存在的路径，如 `/docs` 或 OpenAPI 的 health。）

---

## 6. 本机 FastAPI 建议监听方式

仅本机可连、由 Tunnel 访问即可：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

不要在 `0.0.0.0` 上对外暴露数据库；Postgres 仍建议只监听 `127.0.0.1`。

---

## 7. 与 Vercel 前端配合

1. 在 Vercel 项目环境变量中设置 API 基地址，例如：  
   `NEXT_PUBLIC_API_BASE_URL=https://api.example.com`
2. 在 FastAPI 中为浏览器请求配置 **CORS**，`allow_origins` 至少包含：
   - `https://<你的项目>.vercel.app`
   - 若使用自定义域名：`https://<你的前端域名>`

不要使用 `allow_origins=["*"]` 搭配带 Cookie 的鉴权，除非你很清楚风险。

---

## 8. 安全与运维提示

- **Token / 配置文件**：与 Tunnel 凭证等同 root 级入口，备份加密存储，不要提交到 Git。
- **最小暴露**：Tunnel 只映射需要的 hostname；不需要的子域不要配。
- **Cloudflare 侧**：可在 Zero Trust 里为该应用路径加 **Access 策略**（可选），对未登录用户限制访问（按产品文档配置）。
- **升级**：`sudo apt-get update && sudo apt-get install --only-upgrade cloudflared`。

---

## 9. 常见问题

| 现象 | 排查 |
|------|------|
| `502` / `error code: 1033` | 本机服务未监听、端口写错、或只绑定了别的接口；确认 `curl http://127.0.0.1:8000/...` 在本机成功。 |
| Tunnel 显示 **inactive** | `cloudflared` 未运行或 token 错误；查 `journalctl -u cloudflared`。 |
| 域名无法解析 | 确认域名在 Cloudflare；Public Hostname 保存后 DNS 是否已出现 CNAME 指向 `*.cfargotunnel.com`（以控制台显示为准）。 |
| 仅 SSH 能连、网页不通 | 正常：公网不访问你 IP 的 443，流量走 Cloudflare；检查是否误用 `http://公网IP` 访问。 |

---

## 10. 参考链接

- [Cloudflare Tunnel 文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [cloudflared GitHub](https://github.com/cloudflare/cloudflared)
