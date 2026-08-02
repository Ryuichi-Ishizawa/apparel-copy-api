"""
Apparel Copy API のテスト。
pytestで実行: pytest test_api.py -v
"""

import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

# テスト用の合言葉（サーバーの環境変数と同じ値を硬くコード）
VALID_API_KEY = "my-secret-key-123"


def test_health():
    """ヘルスチェック（認証不要）"""
    res = client.get("/")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_generate_copy_no_key():
    """キー無し → 401"""
    res = client.post(
        "/generate-copy",
        data={"gender": "auto"},
        files={"images": ("test.jpg", b"dummy")},
    )
    assert res.status_code == 401
    assert "APIキー" in res.json()["detail"]


def test_generate_copy_wrong_key():
    """キー間違い → 401"""
    res = client.post(
        "/generate-copy",
        headers={"X-API-Key": "wrong-key"},
        data={"gender": "auto"},
        files={"images": ("test.jpg", b"dummy")},
    )
    assert res.status_code == 401


def test_extract_facts_no_key():
    """extract_facts、キー無し → 401"""
    res = client.post("/extract-facts", data={"source_text": "test"})
    assert res.status_code == 401


def test_extract_facts_with_key():
    """extract_facts、正しいキー + テキスト → 200（実際の処理は走る）"""
    res = client.post(
        "/extract-facts",
        headers={"X-API-Key": VALID_API_KEY},
        data={"source_text": "Material: Cotton 100% / Size: S,M,L"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "known_facts_ja" in data
    assert "not_found" in data