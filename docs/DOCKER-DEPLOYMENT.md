# ScriptNow Docker 部署指南

本文描述 ScriptNow 当前唯一受支持的容器化生产安装方式。容器仅监听本机地址，由宝塔、Nginx 或其他入口网关负责域名与 TLS。

## 1. 安装 Docker Engine

以下命令适用于 Ubuntu 与 Debian。不要使用来源不明的一键脚本安装生产环境 Docker。

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
docker compose version
```

若服务器无法稳定访问 Docker 官方仓库，应在服务器或云厂商层配置可信的 Docker 镜像加速器。ScriptNow 不在代码中写死某个地区镜像。

## 2. 准备部署配置

```bash
cd /zjdata/dk_project/dk_app/scripnow/scriptnow
cp deploy.env.example deploy.env
chmod 600 deploy.env
```

分别生成两个生产密钥并写入 `deploy.env`，不要复用同一个值：

```bash
openssl rand -hex 32
openssl rand -hex 32
```

默认配置把服务绑定到 `127.0.0.1:18090`。如需更换端口，只修改 `deploy.env` 中的 `PORT`，不要直接修改 Compose 文件。

### 国内网络构建加速

官方源连接较慢时，可在 `deploy.env` 中显式启用镜像：

```dotenv
NPM_REGISTRY=https://registry.npmmirror.com
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
```

这些配置只影响镜像构建，不进入应用业务配置。镜像不可用时删除对应覆盖项即可回到官方源。

## 3. 构建并启动

```bash
docker compose --env-file deploy.env build --pull
docker compose --env-file deploy.env up -d --remove-orphans
docker compose --env-file deploy.env ps
curl -fsS http://127.0.0.1:18090/health
```

在仓库根目录也可以使用等价的快捷命令：

```bash
make docker-build
make docker-up
```

这些命令同样强制读取 `scriptnow/deploy.env`；文件缺失时会直接停止并给出修复提示。

健康检查应返回包含 `status` 的 JSON。容器名由 Compose 管理，可通过以下命令查看，不在配置中写死：

```bash
docker compose --env-file deploy.env ps --format json
```

## 4. 宝塔反向代理

在宝塔中把站点反向代理到：

```text
http://127.0.0.1:18090
```

域名、证书续期、HTTP 到 HTTPS 跳转均由宝塔负责。生产配置必须保持：

```dotenv
SCRIPTNOW_COOKIE_SECURE=true
```

不要把容器端口绑定到 `0.0.0.0`，也不要把 `deploy.env`、数据库或上传目录暴露为静态资源。

## 5. 升级、日志与备份

升级应用：

```bash
git pull --ff-only
cd scriptnow
docker compose --env-file deploy.env up -d --build --remove-orphans
curl -fsS http://127.0.0.1:18090/health
```

查看日志：

```bash
docker compose --env-file deploy.env logs --tail=200 app
docker compose --env-file deploy.env logs -f app
```

备份 SQLite 数据库：

```bash
mkdir -p backups
docker compose --env-file deploy.env cp app:/app/data/scriptnow.db \
  "backups/scriptnow-$(date +%Y%m%d-%H%M%S).db"
```

停止服务不会删除数据：

```bash
docker compose --env-file deploy.env down
```

不要在未备份时执行 `docker compose down -v`，该命令会删除持久化数据卷。

## 6. 常见问题

- **Compose 提示缺少密钥**：复制 `deploy.env.example` 并设置两个随机密钥；系统不再接受可预测的生产默认值。
- **构建时 npm、pip 或 apt 超时**：启用上面的国内镜像覆盖，或检查服务器 DNS 与出口网络。
- **反向代理出现 502**：先在服务器执行 `curl http://127.0.0.1:18090/health`，再检查 `docker compose ps` 和容器日志。
- **登录后 Cookie 丢失**：确认外部访问使用 HTTPS，宝塔传递了正确的 `Host` 与 `X-Forwarded-Proto`。
