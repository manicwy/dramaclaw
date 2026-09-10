<!-- lang-switch -->
[English](../../en/guides/source-build.md) · **简体中文**

# 源码构建部署与初始化

> 本地改了 DramaClaw 或 `dramaclaw-gateway` 代码时，用这份手册从源码构建并完成首次配置。只想拉已发布镜像，请看 [快速开始](../getting-started/quickstart.md) 或 [自托管手册](self-hosting.md)。

三个服务全部本地产出：`api`（本仓）、`web`（本仓 `frontend/`）、`newapi`（旁边的 `dramaclaw-gateway` checkout）。镜像名是 `dramaclaw-local/*`，不会覆盖本机缓存里的 `claymorelab/*` 发布镜像。

不要用 `docker-compose.release.yml`：那份文件只拉已发布镜像，带不上你的本地改动。

## 1. 前置

- Docker + Docker Compose ≥ 2.24（`docker compose version`）。
- 建议 ≥ 2 vCPU / 4GB（不含模型推理）。
- 两个 git checkout 并排放：

```text
<工作目录>/
  dramaclaw/            # 本仓
  dramaclaw-gateway/    # 内置网关源码
```

网关 clone 不在默认位置时，在 `dramaclaw/.env` 里设 `DRAMACLAW_GATEWAY_SRC` 为实际路径，或设成 git 地址，例如 `https://github.com/dramaclaw/dramaclaw-gateway.git#main`。缺网关上下文时，构建会报 `unable to prepare context`。

## 2. 准备配置

在 **`dramaclaw/`** 下操作，只改这份 `.env`：

```bash
cd dramaclaw
cp .env.example .env
```

**不要配 `dramaclaw-gateway/.env`。** 源码构建时，Compose 只把该目录当构建上下文；容器运行环境由 `docker-compose.release.yml` 注入（`SQL_DSN=""`、`TZ=Asia/Shanghai`，数据落在 `newapi-data` 卷）。上游渠道、模型映射、token 也不要写进网关 `.env`，起栈后在网页或网关后台配置。

### 必改

| 变量 | 说明 |
|---|---|
| `PROMPT_EXPORT_PASSWORD` | 提示词导出口令。默认 `change_me`，部署前必须改掉。 |

### 按需

| 变量 | 何时改 |
|---|---|
| `ST_NEWAPI_PORT` | 宿主 3000 被占用时改映射端口。容器内仍是 3000。 |
| `ST_NEWAPI_BIND` | 默认 `127.0.0.1`。要从别的机器进网关后台时设 `0.0.0.0`。 |
| `DRAMACLAW_GATEWAY_SRC` | 网关源码不在 `../dramaclaw-gateway` 时。 |
| `NEWAPI_PROVISIONER_ENABLED` | 默认 `true`。设 `false` 可关掉设置页的一键初始化。 |
| `INSTALL_WORLD` | 需要 3DGS/SHARP 时：`INSTALL_WORLD=1 docker compose up -d --build`。 |

`NEWAPI_ADMIN_BASE_URL` 在 Compose 里会被改成 `http://newapi:3000`，容器内不要改成 `127.0.0.1`。渠道地址和运行 token 保存在本机 `settings.db`，不从环境变量读。

### 参考媒体 relay（参考图 / 参考视频）

纯文本 → 成片可以先不配。要用参考图时，在 **`dramaclaw/.env`** 里选一种：

**阿里云 OSS（默认）**

```bash
MEDIA_RELAY_PROVIDER=aliyun_oss
OSS_RELAY_ENDPOINT=oss-cn-chengdu.aliyuncs.com
OSS_RELAY_BUCKET=
OSS_RELAY_AK=
OSS_RELAY_SK=
```

网页「媒体存储」保存后，数据库配置会覆盖这些环境变量。

**腾讯云 COS**

```bash
MEDIA_RELAY_PROVIDER=cos
COS_RELAY_BUCKET=
COS_RELAY_REGION=ap-guangzhou
COS_RELAY_SECRET_ID=
COS_RELAY_SECRET_KEY=
```

COS **只认环境变量**。网页「媒体存储」目前只支持 OSS / Cloudinary；在该页保存后，provider 会回落到 `aliyun_oss`。用 COS 时不要在网页保存媒体存储。

**Cloudinary**：把 `MEDIA_RELAY_PROVIDER` 设为 `cloudinary`，并填写 `CLOUDINARY_RELAY_*`。

完整变量见 [环境变量参考](../reference/environment-variables.md)。

## 3. 构建并启动

```bash
cd dramaclaw
docker compose up -d --build
docker compose ps
```

`api`、`newapi`、`web` 均应为 running。首次构建网关（Go + bun）要几分钟。

| 地址 | 用途 |
|---|---|
| <http://localhost:8080> | 浏览器界面（只跟 `web` 说话） |
| <http://localhost:8780> | REST API |
| <http://127.0.0.1:3000> | 内置网关管理后台（默认只绑本机） |

```bash
docker compose logs -f api          # 看后端
docker compose logs -f newapi       # 看网关
docker compose down                 # 停止，保留数据卷
```

不要加 `-v`，否则会删掉 `ce-data` 和 `newapi-data`。

### 改代码后重建

| 改了什么 | 命令 |
|---|---|
| DramaClaw 后端（`src/`） | `docker compose up -d --build api` |
| 前端（`frontend/`） | `docker compose up -d --build web` |
| 网关（`../dramaclaw-gateway`） | `docker compose up -d --build newapi` |
| 两边都改了 | `docker compose up -d --build` |

只改 `.env`、没改代码时，`docker compose up -d` 会重建受影响的容器，不必 `--build`。COS / OSS 密钥改完后重启 `api`：

```bash
docker compose up -d api
```

## 4. 首次初始化

打开 <http://localhost:8080> → **设置 → 模型配置**。页面顶部「当前生效」是实际运行模式，不是当前标签。

### A. 官方（最快）

1. 到 <https://relayclaw.cdnfg.com> 领取 DC key。
2. 打开 **官方**，粘贴 key。
3. 点 **保存并启用**。

无需映射模型。内置网关此时闲置待命。

### B. 自定义（走本地网关）

1. 打开 **自定义**。状态若是「等待初始化」：
   - 为全新网关设置 root 密码（至少 8 位）并确认。
   - 点 **初始化本地 NewAPI**。
2. 向导会创建管理员（已初始化则跳过），并创建或复用 `dramaclaw-ce-runtime` 运行令牌。
3. 到 <http://127.0.0.1:3000> 添加上游渠道，再回到设置页把 DramaClaw 逻辑模型映射到真实上游模型。

也可直接打开网关后台完成首启向导，再回到 DramaClaw 设置页继续映射。

### C. 本地 + 官方混合

先按 A 保存官方 DC key，再按 B 初始化本地网关。主链路走官方，额外渠道（例如本地 ComfyUI）走内置网关。

更细的渠道、Embedding、媒体模型步骤见 [配置模型供应商](../getting-started/configuring-models.md)。

## 5. 确认

```bash
docker compose ps
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8080
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8780/api/v1/config
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/api/status
```

设置页应能看到已启用的模式。用参考图时，确认 `.env` 里的 relay 已填，且用 COS 时没有在网页「媒体存储」里保存过。

## 6. 常见问题

| 现象 | 处理 |
|---|---|
| `unable to prepare context ... dramaclaw-gateway` | 并排 clone 网关，或设 `DRAMACLAW_GATEWAY_SRC`。 |
| 改了代码界面/接口没变 | 用了 `docker-compose.release.yml`，或忘了 `--build`。回到 `docker compose up -d --build`。 |
| 配了 `dramaclaw-gateway/.env` 不生效 | 源码构建不读这份文件。改 `dramaclaw/.env` 后 `docker compose up -d api`。 |
| COS 参考图仍走 OSS | 网页「媒体存储」覆盖了环境变量。用 COS 时不要在该页保存。 |
| 3000 端口占用 | `.env` 设 `ST_NEWAPI_PORT` 后重新 `docker compose up -d`。`api` 不等网关健康，不会被卡住。 |
| 8780 占用 | `.env` 设 `ST_API_PORT`。 |
| 自定义初始化超时 / `Request timed out .../newapi/init` | 页面会传 `http://127.0.0.1:3000`，api 容器内应改走 `http://newapi:3000`。源码构建请重建 api 后再点一次初始化。 |
| `No available channel for model ...` | 自定义模式下检查渠道是否启用、逻辑模型映射和上游模型名。 |

备份、升级、数据卷见 [自托管手册](self-hosting.md)。平台前置见 [安装指南](../getting-started/installation.md)。
