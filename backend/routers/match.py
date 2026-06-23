"""工具匹配路由 - 为步骤补充工具元信息"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from core.tool_registry import get_tool, get_all_tools

router = APIRouter()


class MatchRequest(BaseModel):
    steps: list[dict]


class MatchResponse(BaseModel):
    steps: list[dict]
    edges: list[dict]
    tools: list[dict]


@router.post("/match", response_model=MatchResponse)
async def match_tools(req: MatchRequest):
    """
    接收步骤数组，补充工具元信息返回完整工作流
    """
    enriched_steps = []
    for step in req.steps:
        tool_name = step.get("tool", "")
        tool = get_tool(tool_name)
        enriched = {
            **step,
            "tool_info": tool.to_dict() if tool else None,
        }
        enriched_steps.append(enriched)

    # 自动生成 edges（按步骤顺序连接）
    edges = []
    for i in range(len(enriched_steps) - 1):
        edges.append({
            "from": enriched_steps[i]["id"],
            "to": enriched_steps[i + 1]["id"],
        })

    return MatchResponse(
        steps=enriched_steps,
        edges=edges,
        tools=get_all_tools(),
    )


@router.get("/tools")
async def list_tools():
    """获取所有可用工具列表"""
    return {"tools": get_all_tools()}
