"""导出路由 - 工作流 → TRAE Skill / JSON"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from exporters.trae_skill import export_to_trae_skill, export_to_trae_skill_yaml
from exporters.json_export import export_to_json

router = APIRouter()


class ExportRequest(BaseModel):
    workflow: dict
    format: str = "trae_skill"  # trae_skill | trae_skill_yaml | json


class ExportResponse(BaseModel):
    format: str
    content: str
    filename: str


@router.post("/export", response_model=ExportResponse)
async def export_workflow(req: ExportRequest):
    """
    接收工作流 JSON + 格式参数，返回导出内容
    支持格式：trae_skill（JSON）/ trae_skill_yaml / json
    """
    workflow = req.workflow
    fmt = req.format

    if fmt == "trae_skill":
        content = export_to_trae_skill(workflow)
        filename = "flowgenie_skill.json"
    elif fmt == "trae_skill_yaml":
        content = export_to_trae_skill_yaml(workflow)
        filename = "flowgenie_skill.yaml"
    elif fmt == "json":
        content = export_to_json(workflow)
        filename = "flowgenie_workflow.json"
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {fmt}")

    return ExportResponse(format=fmt, content=content, filename=filename)
