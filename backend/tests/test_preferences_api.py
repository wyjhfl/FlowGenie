"""preferences API 集成测试 - schema / GET / PUT / DELETE / 脱敏 / key 校验

覆盖:
- GET /api/preferences/schema:返回偏好定义列表,含 secret 类型标记
- GET /api/preferences:空库返回空 dict
- PUT /api/preferences:写入后 GET 返回明文(text 类型)
- PUT 未知 key → 400
- GET 脱敏:secret 类型偏好不返回明文(****后4位)
- DELETE:删除后 GET 不再返回
- DELETE 未知 key → 400
- DELETE 合法 key 但未存储 → 404
"""
import pytest


@pytest.mark.asyncio
async def test_get_preferences_schema(client):
    """schema 端点返回偏好定义列表,slack_webhook_url 标记为 secret"""
    resp = await client.get("/api/preferences/schema")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list) and len(items) > 0
    keys = {it["key"] for it in items}
    assert "email" in keys
    assert "slack_webhook_url" in keys
    slack = next(it for it in items if it["key"] == "slack_webhook_url")
    assert slack["type"] == "secret"


@pytest.mark.asyncio
async def test_get_preferences_empty(client):
    """空库 GET 返回空 dict"""
    resp = await client.get("/api/preferences")
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_put_and_get_preference(client):
    """PUT 写入 text 类型偏好后 GET 返回明文"""
    resp = await client.put(
        "/api/preferences",
        json={"preferences": {"email": "user@example.com"}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": True}

    get_resp = await client.get("/api/preferences")
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_put_preference_unknown_key_rejected(client):
    """PUT 含未知 key 返回 400"""
    resp = await client.put(
        "/api/preferences",
        json={"preferences": {"not_a_real_key": "x"}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_preferences_secret_masked(client):
    """secret 类型偏好 GET 时脱敏,不返回明文"""
    secret_value = "https://hooks.slack.com/services/verylongsecret1234"
    put_resp = await client.put(
        "/api/preferences",
        json={"preferences": {"slack_webhook_url": secret_value}},
    )
    assert put_resp.status_code == 200

    get_resp = await client.get("/api/preferences")
    assert get_resp.status_code == 200
    val = get_resp.json()["slack_webhook_url"]
    # 脱敏:**** + 后4位
    assert val == "****1234"
    assert secret_value not in val


@pytest.mark.asyncio
async def test_delete_preference(client):
    """DELETE 删除后 GET 不再返回该偏好"""
    await client.put(
        "/api/preferences",
        json={"preferences": {"email": "a@b.com"}},
    )
    del_resp = await client.delete("/api/preferences/email")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"success": True}

    get_resp = await client.get("/api/preferences")
    assert "email" not in get_resp.json()


@pytest.mark.asyncio
async def test_delete_preference_unknown_key_rejected(client):
    """DELETE 未知 key 返回 400"""
    resp = await client.delete("/api/preferences/not_a_real_key")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_preference_not_found(client):
    """DELETE 合法 key 但未存储返回 404"""
    # email 是合法 key,但当前库未写入
    resp = await client.delete("/api/preferences/email")
    assert resp.status_code == 404
