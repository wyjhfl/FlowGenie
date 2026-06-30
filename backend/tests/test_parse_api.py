"""parse API 集成测试 - LLM 解析 / refine / 模板匹配顺序 / 输入校验

覆盖:
- 空 requirement → 400
- 自动模式优先 LLM(mock _try_llm_parse 返回合法工作流)→ source=llm
- use_template=True 强制模板:RSS 关键词命中 rss_summary
- 模板匹配顺序:特定模板(daily_news_briefing)优先于通用模板(news_summary)
- LLM 失败 + 无模板匹配 → 兜底 mock
- refine 成功(mock _try_llm_refine)→ source=refine
- refine 未配置 API Key → 503
- refine 空 instruction → 400

LLM 调用通过 patch _try_llm_parse / _try_llm_refine / has_api_key mock,不真实调用。
"""
import pytest
from unittest.mock import patch
from templates import rss_summary, daily_news_briefing, news_summary


def _llm_workflow():
    """构造 LLM mock 返回的合法工作流(工具与必填参数均满足校验)"""
    return {
        "scenario": "LLM生成",
        "summary": "LLM 拆解的工作流",
        "steps": [
            {"id": "step_1", "name": "触发", "tool": "manual_trigger", "params": {}},
            {
                "id": "step_2",
                "name": "请求",
                "tool": "http_request",
                "params": {"url": "https://example.com", "method": "GET"},
            },
        ],
        "edges": [{"from": "step_1", "to": "step_2"}],
    }


def _refined_workflow():
    """构造 refine 后的工作流(比原工作流多一步)"""
    return {
        "scenario": "LLM生成",
        "summary": "调整后的工作流",
        "steps": [
            {"id": "step_1", "name": "触发", "tool": "manual_trigger", "params": {}},
            {
                "id": "step_2",
                "name": "请求",
                "tool": "http_request",
                "params": {"url": "https://example.com", "method": "GET"},
            },
            {
                "id": "step_3",
                "name": "写入文件",
                "tool": "file_write",
                "params": {"path": "./out.json", "content": "{{step_2.body}}"},
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
        ],
    }


@pytest.mark.asyncio
async def test_parse_empty_requirement_rejected(client):
    """空 requirement 返回 400"""
    resp = await client.post("/api/parse", json={"requirement": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_parse_llm_success(client):
    """自动模式优先 LLM,mock 返回合法工作流 → source=llm"""
    with patch("routers.parse._try_llm_parse", return_value=_llm_workflow()):
        resp = await client.post(
            "/api/parse",
            json={"requirement": "做一个数据抓取工作流", "use_template": None},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "llm"
    assert len(data["steps"]) == 2
    assert data["scenario"] == "LLM生成"


@pytest.mark.asyncio
async def test_parse_force_template_matches_rss(client):
    """use_template=True 强制模板,RSS 关键词命中 rss_summary"""
    resp = await client.post(
        "/api/parse",
        json={"requirement": "RSS 订阅聚合", "use_template": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "template"
    assert data["summary"] == rss_summary.get_template()["summary"]


@pytest.mark.asyncio
async def test_parse_template_order_specific_before_general(client):
    """特定模板优先于通用模板:每日新闻简报命中 daily_news_briefing 而非 news_summary。

    "新闻" 同时出现在两个模板关键词中,但 match_template 中 daily_news_briefing 先检查,
    故应命中 daily_news_briefing(含翻译步骤)而非 news_summary(含微信推送)。
    """
    resp = await client.post(
        "/api/parse",
        json={"requirement": "每日新闻简报", "use_template": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "template"
    assert data["summary"] == daily_news_briefing.get_template()["summary"]
    assert data["summary"] != news_summary.get_template()["summary"]


@pytest.mark.asyncio
async def test_parse_mock_fallback(client):
    """LLM 失败 + 无模板匹配 → 兜底 mock"""
    with patch("routers.parse._try_llm_parse", return_value=None), \
         patch("routers.parse.match_template", return_value=None):
        resp = await client.post(
            "/api/parse",
            json={"requirement": "任意需求", "use_template": None},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "mock"
    assert len(data["steps"]) >= 1


@pytest.mark.asyncio
async def test_parse_refine_success(client):
    """refine 成功(mock _try_llm_refine)→ source=refine,步骤数增加"""
    with patch("routers.parse.has_api_key", return_value=True), \
         patch("routers.parse._try_llm_refine", return_value=_refined_workflow()):
        resp = await client.post(
            "/api/parse/refine",
            json={
                "current_workflow": _llm_workflow(),
                "instruction": "增加一个文件写入步骤",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "refine"
    assert len(data["steps"]) == 3


@pytest.mark.asyncio
async def test_parse_refine_no_api_key(client):
    """未配置 LLM API Key 时 refine 返回 503"""
    with patch("routers.parse.has_api_key", return_value=False):
        resp = await client.post(
            "/api/parse/refine",
            json={
                "current_workflow": _llm_workflow(),
                "instruction": "修改一下",
            },
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_parse_refine_empty_instruction_rejected(client):
    """空 instruction 返回 400"""
    resp = await client.post(
        "/api/parse/refine",
        json={"current_workflow": _llm_workflow(), "instruction": ""},
    )
    assert resp.status_code == 400
