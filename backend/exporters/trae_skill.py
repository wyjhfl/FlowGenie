"""导出为 TRAE Skill 格式"""
import json
from core.tool_registry import get_tool


def export_to_trae_skill(workflow: dict) -> str:
    """
    将工作流导出为 TRAE Skill 格式（JSON）
    TRAE Skill 结构：name / description / steps / config
    """
    skill = {
        "name": "flowgenie_workflow",
        "description": workflow.get("summary", "FlowGenie 生成的工作流"),
        "version": "1.0.0",
        "scenario": workflow.get("scenario", ""),
        "steps": [],
        "edges": workflow.get("edges", []),
    }

    for step in workflow.get("steps", []):
        tool = get_tool(step.get("tool", ""))
        step_def = {
            "id": step["id"],
            "name": step["name"],
            "description": step.get("description", ""),
            "tool": step.get("tool", ""),
            "tool_display_name": tool.display_name if tool else step.get("tool", ""),
            "tool_icon": tool.icon if tool else "🔧",
            "tool_category": tool.category if tool else "",
            "params": step.get("params", {}),
        }
        skill["steps"].append(step_def)

    return json.dumps(skill, ensure_ascii=False, indent=2)


def export_to_trae_skill_yaml(workflow: dict) -> str:
    """导出为 TRAE Skill 的 YAML 风格文本（简化版）"""
    lines = [
        f"# FlowGenie 生成的 TRAE Skill",
        f"name: flowgenie_workflow",
        f"description: {workflow.get('summary', '')}",
        f"scenario: {workflow.get('scenario', '')}",
        f"version: 1.0.0",
        f"",
        f"steps:",
    ]
    for step in workflow.get("steps", []):
        tool = get_tool(step.get("tool", ""))
        lines.append(f"  - id: {step['id']}")
        lines.append(f"    name: {step['name']}")
        lines.append(f"    tool: {step.get('tool', '')}")
        lines.append(f"    description: {step.get('description', '')}")
        params = step.get("params", {})
        if params:
            lines.append(f"    params:")
            for k, v in params.items():
                lines.append(f"      {k}: {v}")
        else:
            lines.append(f"    params: {{}}")

    lines.append(f"")
    lines.append(f"edges:")
    for edge in workflow.get("edges", []):
        lines.append(f"  - from: {edge['from']}")
        lines.append(f"    to: {edge['to']}")

    return "\n".join(lines)
