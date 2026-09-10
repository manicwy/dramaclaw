"""Tests for the Tencent COS media relay (dependency-free q-sign sha1 URLs)."""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse

import httpx
import pytest

from novelvideo.storage import media_relay
from novelvideo.storage.media_relay import (
    MediaRelayConfigError,
    TencentCOSRelay,
    _cos_presigned_url,
)

BUCKET = "test-bucket"
REGION = "ap-guangzhou"
SECRET_ID = "AKIDtestsecretid"
SECRET_KEY = "test-secret-key"
KEY = "relay/20260101/abc123.png"


def _recompute_signature(
    url: str,
    *,
    method: str,
    key: str,
    secret_key: str,
) -> str:
    """Recompute the q-sign (sha1) signature from values in a presigned URL.

    Mirrors the official ``cos-python-sdk-v5`` ``CosS3Auth`` scheme, so this
    validates the algorithm end-to-end without patching the clock.
    """
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    sign_time = query["q-sign-time"]
    host = f"{BUCKET}.cos.{REGION}.myqcloud.com"
    format_str = "\n".join(
        [
            method.lower(),
            "/" + key,
            "",
            f"host={host}",
        ]
    ) + "\n"
    format_sha1 = hashlib.sha1(format_str.encode("utf-8")).hexdigest()
    str_to_sign = f"sha1\n{sign_time}\n{format_sha1}\n"
    sign_key = hmac.new(
        secret_key.encode("utf-8"), sign_time.encode("utf-8"), hashlib.sha1
    ).hexdigest()
    return hmac.new(
        sign_key.encode("utf-8"), str_to_sign.encode("utf-8"), hashlib.sha1
    ).hexdigest()


def _signed_url(method: str = "GET", ttl: int = 1800) -> str:
    return _cos_presigned_url(
        method=method,
        key=KEY,
        secret_id=SECRET_ID,
        secret_key=SECRET_KEY,
        bucket=BUCKET,
        region=REGION,
        ttl=ttl,
    )


def test_presigned_url_structure_and_signature():
    url = _signed_url()
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))

    assert parsed.scheme == "https"
    assert parsed.netloc == f"{BUCKET}.cos.{REGION}.myqcloud.com"
    assert parsed.path == f"/{KEY}"
    assert query["q-sign-algorithm"] == "sha1"
    assert query["q-ak"] == SECRET_ID
    assert query["q-header-list"] == "host"
    assert query["q-url-param-list"] == ""

    start, end = (int(v) for v in query["q-sign-time"].split(";"))
    now = int(time.time())
    assert start <= now <= end
    assert end - start == 60 + 1800
    assert query["q-key-time"] == query["q-sign-time"]

    assert query["q-signature"] == _recompute_signature(
        url, method="GET", key=KEY, secret_key=SECRET_KEY
    )


def test_presigned_url_is_method_specific():
    put_url = _signed_url(method="PUT")
    get_url = _signed_url(method="GET")
    put_sig = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(put_url).query, keep_blank_values=True))[
        "q-signature"
    ]
    get_sig = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(get_url).query, keep_blank_values=True))[
        "q-signature"
    ]
    assert put_sig != get_sig


def test_presigned_url_encodes_key():
    url = _cos_presigned_url(
        method="GET",
        key="relay/20260101/图片 01.png",
        secret_id=SECRET_ID,
        secret_key=SECRET_KEY,
        bucket=BUCKET,
        region=REGION,
        ttl=1800,
    )
    assert urllib.parse.quote("图片 01.png", safe="") in urllib.parse.urlsplit(url).path


def test_tencent_cos_relay_requires_full_config():
    with pytest.raises(MediaRelayConfigError, match="COS media relay config missing"):
        TencentCOSRelay(bucket="", region=REGION, secret_id=SECRET_ID, secret_key="")


def test_upload_bytes_puts_then_returns_signed_get_url(respx_mock):
    relay = TencentCOSRelay(
        bucket=BUCKET,
        region=REGION,
        secret_id=SECRET_ID,
        secret_key=SECRET_KEY,
    )
    put_route = respx_mock.put(
        url__startswith=f"https://{BUCKET}.cos.{REGION}.myqcloud.com/relay/"
    ).mock(return_value=httpx.Response(200))

    url = relay.upload_bytes(b"fake-image-bytes", ext="png", ttl=1800)

    assert put_route.called
    parsed = urllib.parse.urlsplit(url)
    assert parsed.netloc == f"{BUCKET}.cos.{REGION}.myqcloud.com"
    assert parsed.path.startswith("/relay/")
    assert parsed.path.endswith(".png")
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    assert query["q-signature"] == _recompute_signature(
        url, method="GET", key=parsed.path.lstrip("/"), secret_key=SECRET_KEY
    )


def test_upload_bytes_surfaces_http_error(respx_mock):
    relay = TencentCOSRelay(
        bucket=BUCKET,
        region=REGION,
        secret_id=SECRET_ID,
        secret_key=SECRET_KEY,
    )
    respx_mock.put(url__startswith="https://").mock(
        return_value=httpx.Response(403, text="Access Denied")
    )
    with pytest.raises(MediaRelayConfigError, match="COS media relay upload failed"):
        relay.upload_bytes(b"fake-image-bytes", ttl=1800)


def test_get_media_relay_dispatch_cos(monkeypatch):
    import novelvideo.config as app_config

    monkeypatch.setattr(app_config, "MEDIA_RELAY_PROVIDER", "cos")
    monkeypatch.setattr(app_config, "COS_RELAY_BUCKET", BUCKET)
    monkeypatch.setattr(app_config, "COS_RELAY_REGION", REGION)
    monkeypatch.setattr(app_config, "COS_RELAY_SECRET_ID", SECRET_ID)
    monkeypatch.setattr(app_config, "COS_RELAY_SECRET_KEY", SECRET_KEY)

    relay = media_relay.get_media_relay()
    assert isinstance(relay, TencentCOSRelay)


def test_get_media_relay_dispatch_cos_missing_fields(monkeypatch):
    import novelvideo.config as app_config

    monkeypatch.setattr(app_config, "MEDIA_RELAY_PROVIDER", "cos")
    monkeypatch.setattr(app_config, "COS_RELAY_BUCKET", "")
    monkeypatch.setattr(app_config, "COS_RELAY_REGION", "")
    monkeypatch.setattr(app_config, "COS_RELAY_SECRET_ID", "")
    monkeypatch.setattr(app_config, "COS_RELAY_SECRET_KEY", "")

    with pytest.raises(MediaRelayConfigError, match="COS media relay config missing"):
        media_relay.get_media_relay()


def test_effective_config_env_path_cos(monkeypatch):
    from novelvideo.model_gateway_settings import get_effective_media_relay_config

    monkeypatch.setenv("COS_RELAY_BUCKET", BUCKET)
    monkeypatch.setenv("COS_RELAY_REGION", REGION)
    monkeypatch.setenv("COS_RELAY_SECRET_ID", SECRET_ID)
    monkeypatch.setenv("COS_RELAY_SECRET_KEY", SECRET_KEY)

    cfg = get_effective_media_relay_config(env_provider="cos")

    assert cfg.source == "environment"
    assert cfg.provider == "cos"
    assert cfg.cos_bucket == BUCKET
    assert cfg.cos_region == REGION
    assert cfg.cos_secret_id == SECRET_ID
    assert cfg.cos_secret_key == SECRET_KEY


def test_effective_config_db_priority_over_env(monkeypatch):
    from novelvideo import model_gateway_settings as mgs

    monkeypatch.setattr(mgs, "_uses_ce_gateway_settings", lambda: True)
    monkeypatch.setattr(
        mgs,
        "get_model_gateway_settings",
        lambda: {
            "media_relay_provider": "cos",
            "media_relay_ttl_seconds": "999",
            "cos_relay_bucket": "db-bucket",
            "cos_relay_region": "ap-shanghai",
            "cos_relay_secret_id": "DBID",
            "cos_relay_secret_key": "DBKEY",
        },
    )
    # 环境变量存在也应被数据库配置覆盖（has_db_config 优先）
    monkeypatch.setenv("COS_RELAY_BUCKET", "env-bucket")

    cfg = mgs.get_effective_media_relay_config(env_provider="cos")

    assert cfg.source == "database"
    assert cfg.provider == "cos"
    assert cfg.cos_bucket == "db-bucket"
    assert cfg.cos_region == "ap-shanghai"
    assert cfg.cos_secret_id == "DBID"
    assert cfg.cos_secret_key == "DBKEY"
    assert cfg.ttl_seconds == 999


def test_media_relay_status_cos_masks_secrets_and_configured():
    from novelvideo.model_gateway_settings import build_media_relay_status

    status = build_media_relay_status(
        env_provider="cos",
        env_cos_bucket=BUCKET,
        env_cos_region=REGION,
        env_cos_secret_id=SECRET_ID,
        env_cos_secret_key=SECRET_KEY,
    )

    assert status["provider"] == "cos"
    assert status["cosBucket"] == BUCKET
    assert status["cosRegion"] == REGION
    assert status["configured"] is True
    # 掩码：不泄露明文，保留前 4 后 4
    assert SECRET_ID not in status["cosSecretIdPreview"]
    assert SECRET_KEY not in status["cosSecretKeyPreview"]
    assert status["cosSecretIdPreview"].startswith("AKID")
    assert status["cosSecretIdPreview"].endswith("etid")
    assert status["cosSecretKeyPreview"].startswith("test")
    assert status["cosSecretKeyPreview"].endswith("-key")


def test_media_relay_status_cos_not_configured():
    from novelvideo.model_gateway_settings import build_media_relay_status

    status = build_media_relay_status(
        env_provider="cos",
        env_cos_bucket="",
        env_cos_region="",
        env_cos_secret_id="",
        env_cos_secret_key="",
    )

    assert status["provider"] == "cos"
    assert status["configured"] is False


def test_upload_bytes_uses_safe_object_key(respx_mock):
    relay = TencentCOSRelay(
        bucket=BUCKET,
        region=REGION,
        secret_id=SECRET_ID,
        secret_key=SECRET_KEY,
    )
    object_key = "relay/tenants/org1/projects/proj1/objects/abc123.png"
    respx_mock.put(
        url__startswith=f"https://{BUCKET}.cos.{REGION}.myqcloud.com/{object_key}"
    ).mock(return_value=httpx.Response(200))

    url = relay.upload_bytes(
        b"fake-image-bytes", ext="png", ttl=1800, object_key=object_key
    )

    parsed = urllib.parse.urlsplit(url)
    assert parsed.path == f"/{object_key}"


def test_upload_bytes_rejects_unsafe_object_key():
    from novelvideo.storage.media_relay import ServiceEgressDenied

    relay = TencentCOSRelay(
        bucket=BUCKET,
        region=REGION,
        secret_id=SECRET_ID,
        secret_key=SECRET_KEY,
    )
    with pytest.raises(ServiceEgressDenied):
        relay.upload_bytes(
            b"fake-image-bytes",
            ext="png",
            object_key="../escape.png",
        )
