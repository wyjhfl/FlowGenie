"""导出为通用 JSON 格式"""
import json
from core.tool_registry import get_tool


def export_to_json(workflow: dict) -> str:
    """将工作流导出为通用 JSON 格式（含工具元信息）"""
    export_data = {
        "name": "flowgenie_workflow",
        "summary": workflow.get("summary", ""),
        "scenario": workflow.get("scenario", ""),
        "steps": [],
        "edges": workflow.get("edges", []),
        "exported_by": "FlowGenie",
        "version": "1.0.0",
    }

    for step in workflow.get("steps", []):
        tool = get_tool(step.get("tool", ""))
        step_data = {
            "id": step["id"],
            "name": step["name"],
            "description": step.get("description", ""),
            "tool": step.get("tool", ""),
            "tool_info": tool.to_dict() if tool else None,
            "params": step.get("params", {}),
        }
        export_data["steps"].append(step_data)

    return json.dumps(export_data, ensure_ascii=False, indent=2)
