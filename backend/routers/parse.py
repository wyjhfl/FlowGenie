"""需求拆解路由 - 自然语言 → 工作流"""
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.llm import chat_json, has_api_key
from core.prompts import PARSE_SYSTEM_PROMPT, FEW_SHOT_EXAMPLES, build_parse_user_prompt, REFINE_SYSTEM_PROMPT, build_refine_user_prompt
from core.tool_registry import get_tools_description, get_tool, get_all_tools
from core.validator import validate_workflow
from core.preference_schema import PREFERENCE_ITEMS
from db.database import SessionLocal
from db.models import UserPreference
from templates import (
    news_summary,
    sales_report,
    code_review,
    contract_review,
    sales_quote,
    rss_summary,
    github_monitor,
    telegram_push,
    web_monitor,
    data_analysis,
    daily_news_briefing,
    social_media_monitor,
    meeting_minutes,
    lead_scoring,
    content_localization,
    stock_alert,
    agent_research,
    rag_qa,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    requirement: str
    use_template: Optional[bool] = None  # None=自动(LLM优先), True=强制模板, False=强制LLM


class ParseResponse(BaseModel):
    scenario: str = ""
    summary: str = ""
    steps: list[dict] = []
    edges: list[dict] = []
    source: str  # "template" | "llm" | "mock" | "refine"
    need_clarification: bool = False
    questions: list[str] = []
    on_failure: str = "stop"  # "stop" | "continue"


class RefineRequest(BaseModel):
    current_workflow: dict  # {steps, edges, scenario, summary}
    instruction: str


def enrich_steps_with_tool_info(steps: list[dict]) -> list[dict]:
    """为步骤补充 tool_info 字段，确保前端能显示工具详情"""
    for step in steps:
        tool = get_tool(step.get("tool", ""))
        step["tool_info"] = tool.to_dict() if tool else None
    return steps


def match_template(requirement: str) -> Optional[dict]:
    """根据关键词匹配预定义模板"""
    req_lower = requirement.lower()

    # F1: Agent 自主调研场景（优先匹配,避免 "调研" 被其他模板抢先）
    agent_keywords = agent_research.match_keywords()
    if any(kw in req_lower for kw in agent_keywords):
        return agent_research.get_template()

    # C5: RAG 知识库问答场景(优先匹配,避免 "问答" 被其他模板抢先)
    rag_keywords = rag_qa.match_keywords()
    if any(kw in req_lower for kw in rag_keywords):
        return rag_qa.get_template()

    # RSS 订阅场景（放在新闻摘要之前，避免 "rss" 关键词被 news_summary 抢先匹配）
    rss_keywords = rss_summary.match_keywords()
    if any(kw in req_lower for kw in rss_keywords):
        return rss_summary.get_template()

    # 每日新闻简报场景（放在通用新闻摘要之前，避免 "每日简报" 等关键词被 news_summary 抢先匹配）
    daily_news_keywords = daily_news_briefing.match_keywords()
    if any(kw in req_lower for kw in daily_news_keywords):
        return daily_news_briefing.get_template()

    # 会议纪要场景
    meeting_keywords = meeting_minutes.match_keywords()
    if any(kw in req_lower for kw in meeting_keywords):
        return meeting_minutes.get_template()

    # 销售线索评分场景（放在通用销售报表之前，避免 "销售线索" 等关键词被 sales_report 抢先匹配）
    lead_scoring_keywords = lead_scoring.match_keywords()
    if any(kw in req_lower for kw in lead_scoring_keywords):
        return lead_scoring.get_template()

    # 股价监控告警场景（需放在 social_media_monitor 之前，避免 "股价监控" 中的 "监控" 被抢先匹配）
    stock_alert_keywords = stock_alert.match_keywords()
    if any(kw in req_lower for kw in stock_alert_keywords):
        return stock_alert.get_template()

    # 社媒舆情监控场景（需放在 github_monitor/web_monitor 之前，避免 "监控" 被抢先匹配）
    social_media_keywords = social_media_monitor.match_keywords()
    if any(kw in req_lower for kw in social_media_keywords):
        return social_media_monitor.get_template()

    # GitHub 监控场景（放在代码审查之前，避免 "github" 关键词被 code_review 抢先匹配）
    github_keywords = github_monitor.match_keywords()
    if any(kw in req_lower for kw in github_keywords):
        return github_monitor.get_template()

    # Telegram 推送场景
    telegram_keywords = telegram_push.match_keywords()
    if any(kw in req_lower for kw in telegram_keywords):
        return telegram_push.get_template()

    # 网页监控场景
    web_monitor_keywords = web_monitor.match_keywords()
    if any(kw in req_lower for kw in web_monitor_keywords):
        return web_monitor.get_template()

    # 数据分析场景
    data_analysis_keywords = data_analysis.match_keywords()
    if any(kw in req_lower for kw in data_analysis_keywords):
        return data_analysis.get_template()

    # 内容本地化场景（通用模板，放在已有通用模板之前）
    content_localization_keywords = content_localization.match_keywords()
    if any(kw in req_lower for kw in content_localization_keywords):
        return content_localization.get_template()

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

    # 合同审核场景
    contract_keywords = contract_review.match_keywords()
    if any(kw in req_lower for kw in contract_keywords):
        return contract_review.get_template()

    # 销售报价场景
    quote_keywords = sales_quote.match_keywords()
    if any(kw in req_lower for kw in quote_keywords):
        return sales_quote.get_template()

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
                "params": {"data": "{{step_2.body}}", "task": "分析数据"},
            },
            {
                "id": "step_4",
                "name": "输出结果",
                "description": "写入文件保存结果",
                "tool": "file_write",
                "params": {"path": "./data/result.json", "format": "json", "content": "{{step_3.analysis}}"},
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"},
        ],
    }


def _get_user_preferences() -> dict:
    """查询用户偏好（用于在 LLM 拆解时自动填充参数）"""
    db = SessionLocal()
    try:
        prefs = db.query(UserPreference).all()
        return {p.key: p.value for p in prefs}
    except Exception as e:
        logger.warning(f"查询用户偏好失败: {e}")
        return {}
    finally:
        db.close()


def _build_pref_suffix(user_prefs: dict) -> str:
    """构建用户偏好提示后缀(供 LLM 自动填充工具参数)。

    基于 PREFERENCE_SCHEMA 生成,告知 LLM 每个偏好可填充哪些工具参数。
    """
    if not user_prefs:
        return ""
    pref_lines = []
    for item in PREFERENCE_ITEMS:
        key = item["key"]
        if key not in user_prefs:
            continue
        value = user_prefs[key]
        applicable = item.get("applicable_tools") or {}
        if applicable:
            param_descs = []
            for tool_name, param_names in applicable.items():
                for pn in param_names:
                    param_descs.append(f"{tool_name}.{pn}")
            fill_hint = f"（将自动填充: {', '.join(param_descs)}）"
        else:
            fill_hint = "（执行期配置项）"
        pref_lines.append(f"- {key}{fill_hint}: {value}")
    if not pref_lines:
        return ""
    pref_str = "\n".join(pref_lines)
    return f"\n\n用户偏好（请在生成工作流时自动填充这些值到对应工具参数）：\n{pref_str}"


def _llm_generate_with_retry(
    system_prompt: str,
    base_prompt: str,
    pref_suffix: str,
    tool_names: set,
    allow_clarification: bool = False,
    max_retries: int = 2,
) -> Optional[dict]:
    """调用 LLM 生成工作流,带校验重试。

    :param system_prompt: 系统提示
    :param base_prompt: 基础用户提示(不含偏好后缀)
    :param pref_suffix: 偏好后缀(由 _build_pref_suffix 生成)
    :param tool_names: 合法工具名集合,用于校验
    :param allow_clarification: 是否允许返回澄清请求(parse 场景=True, refine=False)
    :param max_retries: 最大重试次数
    :return: 成功返回 dict,失败返回 None
    """
    user_prompt = base_prompt + pref_suffix
    for attempt in range(max_retries + 1):
        result = chat_json(system_prompt, user_prompt, temperature=0.3)
        if not result:
            break

        # 澄清场景:直接返回,不校验工作流
        if allow_clarification and result.get("need_clarification"):
            return result

        validation = validate_workflow(result, tool_names)
        if validation.valid:
            return result

        # 校验失败:未达重试上限则追加纠错提示重试
        if attempt < max_retries:
            error_text = "\n".join(f"- {e}" for e in validation.errors)
            user_prompt = (
                base_prompt + pref_suffix
                + f"\n\n上一次输出存在以下问题，请修正后重新输出完整 JSON：\n{error_text}"
            )
        else:
            logger.warning(f"LLM 输出校验失败（重试耗尽）: {validation.errors}")
            return None
    return None


def _try_llm_parse(requirement: str) -> Optional[dict]:
    """
    调用 LLM 拆解需求，带校验重试（最多 2 次重试）。
    成功返回 dict（工作流或澄清请求），失败返回 None。
    """
    if not has_api_key():
        return None

    tool_names = {t["name"] for t in get_all_tools()}
    system_prompt = PARSE_SYSTEM_PROMPT.format(
        tools_description=get_tools_description()
    ) + "\n\n" + FEW_SHOT_EXAMPLES

    try:
        pref_suffix = _build_pref_suffix(_get_user_preferences())
        return _llm_generate_with_retry(
            system_prompt=system_prompt,
            base_prompt=build_parse_user_prompt(requirement),
            pref_suffix=pref_suffix,
            tool_names=tool_names,
            allow_clarification=True,
        )
    except Exception as e:
        logger.warning(f"LLM 调用失败: {e}")
        return None


def _try_llm_refine(current_workflow: dict, instruction: str) -> Optional[dict]:
    """
    调用 LLM 增量调整工作流，带校验重试（最多 2 次重试）。
    成功返回 dict（调整后的工作流），失败返回 None。
    """
    if not has_api_key():
        return None

    tool_names = {t["name"] for t in get_all_tools()}
    system_prompt = REFINE_SYSTEM_PROMPT.format(
        tools_description=get_tools_description()
    ) + "\n\n" + FEW_SHOT_EXAMPLES

    try:
        pref_suffix = _build_pref_suffix(_get_user_preferences())
        return _llm_generate_with_retry(
            system_prompt=system_prompt,
            base_prompt=build_refine_user_prompt(current_workflow, instruction),
            pref_suffix=pref_suffix,
            tool_names=tool_names,
            allow_clarification=False,
        )
    except Exception as e:
        logger.warning(f"LLM 调用失败: {e}")
        return None


@router.post("/parse", response_model=ParseResponse)
async def parse_requirement(req: ParseRequest):
    """
    接收自然语言需求，返回拆解后的工作流。
    优先级：强制模板(use_template=True) > 强制LLM(False) / 自动(None) 优先 LLM → 模板回退 → Mock
    """
    requirement = req.requirement.strip()
    if not requirement:
        raise HTTPException(status_code=400, detail="requirement 不能为空")

    # 1. 强制使用模板
    if req.use_template is True:
        template = match_template(requirement)
        if template:
            enrich_steps_with_tool_info(template["steps"])
            return ParseResponse(source="template", on_failure="stop", **template)
        # 没匹配到模板，回退到自动流程
        req.use_template = None

    # 2. 自动模式 / 强制 LLM：优先 LLM 解析（带校验重试）
    if req.use_template is False or req.use_template is None:
        llm_result = await asyncio.to_thread(_try_llm_parse, requirement)
        if llm_result is not None:
            # 澄清场景：直接返回，不补充 tool_info
            if llm_result.get("need_clarification"):
                return ParseResponse(
                    source="llm",
                    scenario="",
                    summary="",
                    steps=[],
                    edges=[],
                    need_clarification=True,
                    questions=llm_result.get("questions", []),
                    on_failure="stop",
                )
            enrich_steps_with_tool_info(llm_result.get("steps", []))
            # 仅提取 ParseResponse 定义的字段，避免 LLM 返回多余字段导致 Pydantic 报错
            filtered = {
                "scenario": llm_result.get("scenario", ""),
                "summary": llm_result.get("summary", ""),
                "steps": llm_result.get("steps", []),
                "edges": llm_result.get("edges", []),
            }
            return ParseResponse(source="llm", on_failure="stop", **filtered)

    # 3. 自动模式：LLM 失败后回退模板匹配
    if req.use_template is None:
        template = match_template(requirement)
        if template:
            enrich_steps_with_tool_info(template["steps"])
            return ParseResponse(source="template", on_failure="stop", **template)

    # 4. 兜底 Mock
    result = mock_parse(requirement)
    enrich_steps_with_tool_info(result["steps"])
    return ParseResponse(source="mock", on_failure="stop", **result)


@router.post("/parse/refine", response_model=ParseResponse)
async def refine_workflow(req: RefineRequest):
    """
    基于现有工作流 + 自然语言调整指令，增量调整工作流。
    请求体：{current_workflow: {steps, edges, scenario, summary}, instruction: str}
    返回：{scenario, summary, steps, edges, source: 'refine'}
    """
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")

    current_workflow = req.current_workflow
    if not isinstance(current_workflow, dict) or not current_workflow.get("steps"):
        raise HTTPException(status_code=400, detail="current_workflow 无效或缺少 steps")

    if not has_api_key():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key，无法执行调整")

    refined = await asyncio.to_thread(_try_llm_refine, current_workflow, instruction)
    if refined is None:
        raise HTTPException(status_code=500, detail="工作流调整失败，请重试或调整指令")

    enrich_steps_with_tool_info(refined.get("steps", []))
    # 仅提取 ParseResponse 定义的字段，避免 LLM 返回多余字段导致 Pydantic 报错
    filtered = {
        "scenario": refined.get("scenario", current_workflow.get("scenario", "")),
        "summary": refined.get("summary", current_workflow.get("summary", "")),
        "steps": refined.get("steps", []),
        "edges": refined.get("edges", []),
    }
    return ParseResponse(source="refine", on_failure="stop", **filtered)
