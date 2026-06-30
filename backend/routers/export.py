"""导出路由 - 工作流 → TRAE Skill / JSON / Python 脚本"""
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from exporters.trae_skill import export_to_trae_skill, export_to_trae_skill_yaml
from exporters.json_export import export_to_json
from exporters.python_script import export_to_python_script

router = APIRouter()


class ExportRequest(BaseModel):
    workflow: dict
    format: str = "trae_skill"  # trae_skill | trae_skill_yaml | json | python_script


class ExportResponse(BaseModel):
    format: str
    content: str
    filename: str
    content_type: str = "text/plain"


def _sanitize_filename(name: str) -> str:
    """将工作流名称转为安全的文件名（仅保留字母数字中文下划线连字符）"""
    safe = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name).strip("_")
    return safe or "flowgenie_workflow"


@router.post("/export", response_model=ExportResponse)
async def export_workflow(req: ExportRequest):
    """
    接收工作流 JSON + 格式参数，返回导出内容
    支持格式：trae_skill（JSON）/ trae_skill_yaml / json / python_script
    """
    workflow = req.workflow
    fmt = req.format

    if fmt == "trae_skill":
        content = export_to_trae_skill(workflow)
        filename = "flowgenie_skill.json"
        content_type = "application/json"
    elif fmt == "trae_skill_yaml":
        content = export_to_trae_skill_yaml(workflow)
        filename = "flowgenie_skill.yaml"
        content_type = "text/yaml"
    elif fmt == "json":
        content = export_to_json(workflow)
        filename = "flowgenie_workflow.json"
        content_type = "application/json"
    elif fmt == "python_script":
        content = export_to_python_script(workflow)
        workflow_name = _sanitize_filename(workflow.get("summary") or "flowgenie_workflow")
        filename = f"{workflow_name}.py"
        content_type = "text/x-python"
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {fmt}")

    return ExportResponse(format=fmt, content=content, filename=filename, content_type=content_type)
