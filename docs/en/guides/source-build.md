<!-- lang-switch -->
**English** · [简体中文](../../zh/guides/source-build.md)

# Source-Build Deploy and First-Time Setup

> Use this runbook when you have local changes in DramaClaw or `dramaclaw-gateway` and need to build from source. To pull published images only, see [Quickstart](../getting-started/quickstart.md) or [Self-Hosting](self-hosting.md).

All three services are built locally: `api` (this repo), `web` (`frontend/` in this repo), and `newapi` (the sibling `dramaclaw-gateway` checkout). Images are named `dramaclaw-local/*` and do not overwrite cached `claymorelab/*` release images.

Do not use `docker-compose.release.yml`. That file only pulls published images and will not include your local changes.

## 1. Prerequisites

- Docker + Docker Compose ≥ 2.24 (`docker compose version`).
- Recommended: ≥ 2 vCPU / 4GB (excluding model inference).
- Two git checkouts side by side:

```text
<workdir>/
  dramaclaw/            # this repo
  dramaclaw-gateway/    # bundled gateway source
```

If the gateway clone is not at the default path, set `DRAMACLAW_GATEWAY_SRC` in `dramaclaw/.env` to the real path, or to a git URL such as `https://github.com/dramaclaw/dramaclaw-gateway.git#main`. Missing gateway context produces `unable to prepare context`.

## 2. Prepare configuration

Work under **`dramaclaw/`**. Edit only this `.env`:

```bash
cd dramaclaw
cp .env.example .env
```

**Do not configure `dramaclaw-gateway/.env`.** In the source-build path, Compose uses that directory only as a build context. Runtime env comes from `docker-compose.release.yml` (`SQL_DSN=""`, `TZ=Asia/Shanghai`, data on the `newapi-data` volume). Do not put upstream channels, model mappings, or tokens in the gateway `.env`; configure those in the web UI or gateway admin after the stack is up.

### Required

| Variable | Notes |
|---|---|
| `PROMPT_EXPORT_PASSWORD` | Prompt-export password. Default is `change_me`; change it before deploy. |

### Optional

| Variable | When to change |
|---|---|
| `ST_NEWAPI_PORT` | Host port if 3000 is taken. Container port stays 3000. |
| `ST_NEWAPI_BIND` | Default `127.0.0.1`. Set `0.0.0.0` to reach the gateway admin from another machine. |
| `DRAMACLAW_GATEWAY_SRC` | When gateway source is not at `../dramaclaw-gateway`. |
| `NEWAPI_PROVISIONER_ENABLED` | Default `true`. Set `false` to disable one-click init on the settings page. |
| `INSTALL_WORLD` | For 3DGS/SHARP: `INSTALL_WORLD=1 docker compose up -d --build`. |

Compose overrides `NEWAPI_ADMIN_BASE_URL` to `http://newapi:3000`. Do not change that to `127.0.0.1` inside the container. Channel URLs and the runtime token are stored in local `settings.db`, not read from env.

### Reference-media relay (reference images / videos)

A text-only → film flow can skip this. For reference images, pick one provider in **`dramaclaw/.env`**:

**Aliyun OSS (default)**

```bash
MEDIA_RELAY_PROVIDER=aliyun_oss
OSS_RELAY_ENDPOINT=oss-cn-chengdu.aliyuncs.com
OSS_RELAY_BUCKET=
OSS_RELAY_AK=
OSS_RELAY_SK=
```

Saving **Media Storage** in the web UI makes the database settings override these variables.

**Tencent Cloud COS**

```bash
MEDIA_RELAY_PROVIDER=cos
COS_RELAY_BUCKET=
COS_RELAY_REGION=ap-guangzhou
COS_RELAY_SECRET_ID=
COS_RELAY_SECRET_KEY=
```

COS is **env-only**. The web **Media Storage** page currently supports OSS / Cloudinary; saving there falls the provider back to `aliyun_oss`. Do not save Media Storage when using COS.

**Cloudinary**: set `MEDIA_RELAY_PROVIDER=cloudinary` and fill in `CLOUDINARY_RELAY_*`.

Full variable list: [Environment Variables](../reference/environment-variables.md).

## 3. Build and start

```bash
cd dramaclaw
docker compose up -d --build
docker compose ps
```

`api`, `newapi`, and `web` should all be running. The first gateway build (Go + bun) takes a few minutes.

| URL | Purpose |
|---|---|
| <http://localhost:8080> | Browser UI (talks only to `web`) |
| <http://localhost:8780> | REST API |
| <http://127.0.0.1:3000> | Bundled gateway admin (loopback only by default) |

```bash
docker compose logs -f api          # backend
docker compose logs -f newapi       # gateway
docker compose down                 # stop, keep volumes
```

Do not add `-v`, or `ce-data` and `newapi-data` will be deleted.

### Rebuild after code changes

| What changed | Command |
|---|---|
| DramaClaw backend (`src/`) | `docker compose up -d --build api` |
| Frontend (`frontend/`) | `docker compose up -d --build web` |
| Gateway (`../dramaclaw-gateway`) | `docker compose up -d --build newapi` |
| Both | `docker compose up -d --build` |

If you only changed `.env`, `docker compose up -d` recreates affected containers; `--build` is not required. After changing COS / OSS keys, restart `api`:

```bash
docker compose up -d api
```

## 4. First-time setup

Open <http://localhost:8080> → **Settings → Model Configuration**. The “currently active” label at the top is the live mode, not the tab you are viewing.

### A. Official (fastest)

1. Get a DC key at <https://relayclaw.cdnfg.com>.
2. Open **Official** and paste the key.
3. Click **Save and Enable**.

No model mapping is required. The bundled gateway stays idle.

### B. Custom (local gateway)

1. Open **Custom**. If the status is “waiting for initialization”:
   - Set a root password for a fresh gateway (at least 8 characters) and confirm.
   - Click **Initialize local NewAPI**.
2. The wizard creates the admin (skipped if already initialized) and creates or reuses the `dramaclaw-ce-runtime` token.
3. Add upstream channels at <http://127.0.0.1:3000>, then map DramaClaw logical models to real upstream models on the settings page.

You can also finish the gateway first-run wizard in the admin UI, then return to DramaClaw settings to continue mapping.

### C. Local + Official Hybrid

Save the official DC key as in A, then initialize the local gateway as in B. The main path uses official models; extra channels (for example local ComfyUI) go through the bundled gateway.

For channels, embeddings, and media models, see [Configuring Model Providers](../getting-started/configuring-models.md).

## 5. Verify

```bash
docker compose ps
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8080
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8780/api/v1/config
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/api/status
```

The settings page should show the enabled mode. For reference images, confirm the relay fields in `.env`, and that you have not saved **Media Storage** in the UI if you are using COS.

## 6. Common issues

| Symptom | What to do |
|---|---|
| `unable to prepare context ... dramaclaw-gateway` | Clone the gateway next to this repo, or set `DRAMACLAW_GATEWAY_SRC`. |
| Code changes do not show up | You used `docker-compose.release.yml`, or forgot `--build`. Use `docker compose up -d --build`. |
| Edits to `dramaclaw-gateway/.env` have no effect | Source-build does not read that file. Edit `dramaclaw/.env` and run `docker compose up -d api`. |
| COS reference images still hit OSS | **Media Storage** in the UI overrode env. Do not save that page when using COS. |
| Port 3000 in use | Set `ST_NEWAPI_PORT` in `.env` and run `docker compose up -d`. `api` does not wait for gateway health. |
| Port 8780 in use | Set `ST_API_PORT`. |
| `No available channel for model ...` | In Custom mode, check that the channel is enabled and the logical-to-upstream mapping is correct. |

Backup, upgrade, and volumes: [Self-Hosting](self-hosting.md). Platform prerequisites: [Installation](../getting-started/installation.md).
