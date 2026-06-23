"""需求拆解路由 - 自然语言 → 工作流"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.llm import chat_json, has_api_key
from core.prompts import PARSE_SYSTEM_PROMPT, build_parse_user_prompt
from core.tool_registry import get_tools_description, get_tool
from templates import news_summary, sales_report, code_review

router = APIRouter()


class ParseRequest(BaseModel):
    requirement: str
    use_template: Optional[bool] = None  # None=自动判断, True=强制模板, False=强制LLM


class ParseResponse(BaseModel):
    scenario: str
    summary: str
    steps: list[dict]
    edges: list[dict]
    source: str  # "template" | "llm" | "mock"


def match_template(requirement: str) -> Optional[dict]:
    """根据关键词匹配预定义模板"""
    req_lower = requirement.lower()

    # 新闻摘要场景
    news_keywords = news_summary.match_keywords()
    if any(kw in req_lower for kw in news_keywords):
        return news_summary.get_template()

    # 销售报表场景
    sales_keywords = sales_report.match_keywords()
    if any(kw in req_lower for kw in sales_keywords):
        return sales_report.get_template()

    # Code Review 场景
    review_keywords = code_review.match_keywords()
    if any(kw in req_lower for kw in review_keywords):
        return code_review.get_template()

    return None


def mock_parse(requirement: str) -> dict:
    """无 API Key 时的兜底 Mock 响应"""
    return {
        "scenario": "通用自动化",
        "summary": f"根据需求「{requirement}」生成的示例工作流",
        "steps": [
            {
                "id": "step_1",
                "name": "触发工作流",
                "description": "手动触发执行",
                "tool": "manual_trigger",
                "params": {},
            },
            {
                "id": "step_2",
                "name": "获取数据",
                "description": "通过 HTTP 请求获取数据",
                "tool": "http_request",
                "params": {"url": "https://api.example.com/data", "method": "GET"},
            },
            {
                "id": "step_3",
                "name": "AI 处理",
                "description": "用 LLM 处理数据",
                "tool": "llm_analysis",
                "params": {"model": "deepseek-chat", "task": "分析数据"},
            },
            {
                "id": "step_4",
                "name": "输出结果",
                "description": "写入文件保存结果",
                "tool": "file_write",
                "params": {"path": "/output/result.json", "format": "json"},
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"},
        ],
    }


@router.post("/parse", response_model=ParseResponse)
async def parse_requirement(req: ParseRequest):
    """
    接收自然语言需求，返回拆解后的工作流
    优先级：强制模板 > 强制LLM > 自动匹配模板 > LLM 拆解 > Mock
    """
    requirement = req.requirement.strip()
    if not requirement:
        raise HTTPException(status_code=400, detail="requirement 不能为空")

    # 1. 强制使用模板
    if req.use_template is True:
        template = match_template(requirement)
        if template:
            return ParseResponse(source="template", **template)
        # 没匹配到模板，回退到自动流程
        req.use_template = None

    # 2. 自动模式：先尝试模板匹配（保证 Demo 稳定）
    if req.use_template is None:
        template = match_template(requirement)
        if template:
            return ParseResponse(source="template", **template)

    # 3. 调用 LLM 拆解
    if has_api_key():
        try:
            system_prompt = PARSE_SYSTEM_PROMPT.format(
                tools_description=get_tools_description()
            )
            user_prompt = build_parse_user_prompt(requirement)
            result = chat_json(system_prompt, user_prompt, temperature=0.3)

            if result and "steps" in result:
                # 补全工具元信息
                for step in result.get("steps", []):
                    if "tool" in step and not get_tool(step["tool"]):
                        # 工具不在库中，保留但标记
                        step.setdefault("params", {})
                return ParseResponse(source="llm", **result)
        except Exception as e:
            # LLM 调用失败，回退到 Mock
            pass

    # 4. 兜底 Mock
    result = mock_parse(requirement)
    return ParseResponse(source="mock", **result)
