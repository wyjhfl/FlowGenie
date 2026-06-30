"""export API 集成测试 - python_script / trae_skill / json 导出 + AST 安全检查

覆盖:
- python_script 导出:返回脚本内容,含工具函数与拓扑执行引擎
- AST 安全检查:导出脚本可解析,不含危险模块/调用(code_node 未使用时)
- trae_skill / json 格式:返回合法 JSON,字段正确
- 未知格式 → 400
- 文件名从 summary 派生并做安全化

注:export 路由接收完整 workflow dict(非 workflow id),无 DB 查找,故不存在 404 场景;
不支持的格式由路由返回 400。
"""
import ast
import json
import pytest


def _sample_workflow(summary="示例工作流", steps=None, edges=None):
    """构造导出请求用的工作流 dict"""
    if steps is None:
        steps = [
            {"id": "step_1", "name": "触发", "tool": "manual_trigger", "params": {}},
            {
                "id": "step_2",
                "name": "请求",
                "tool": "http_request",
                "params": {"url": "https://api.example.com", "method": "GET"},
            },
        ]
    if edges is None:
        edges = [{"from": "step_1", "to": "step_2"}]
    return {
        "scenario": "测试场景",
        "summary": summary,
        "steps": steps,
        "edges": edges,
    }


_DANGEROUS_MODULES = {"subprocess", "ctypes", "socket", "shutil"}


@pytest.mark.asyncio
async def test_export_python_script(client):
    """python_script 格式返回可执行 Python 脚本"""
    resp = await client.post(
        "/api/export",
        json={"workflow": _sample_workflow(), "format": "python_script"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "python_script"
    assert data["content_type"] == "text/x-python"
    assert data["filename"].endswith(".py")
    assert "execute_workflow" in data["content"]


@pytest.mark.asyncio
async def test_export_python_script_contains_tools_and_engine(client):
    """导出脚本包含工具函数实现与拓扑执行引擎、主入口"""
    resp = await client.post(
        "/api/export",
        json={"workflow": _sample_workflow(), "format": "python_script"},
    )
    content = resp.json()["content"]
    # 工具函数实现
    assert "async def http_request(params):" in content
    # 拓扑执行引擎 + 拓扑排序所需数据结构
    assert "async def execute_workflow(" in content
    assert "deque(" in content
    # 主入口
    assert 'if __name__ == "__main__":' in content


@pytest.mark.asyncio
async def test_export_python_script_ast_safe(client):
    """导出脚本可通过 AST 解析且不含危险模块/调用(未使用 code_node)"""
    resp = await client.post(
        "/api/export",
        json={"workflow": _sample_workflow(), "format": "python_script"},
    )
    content = resp.json()["content"]

    # 1. 语法合法
    tree = ast.parse(content)

    # 2. 无危险模块导入
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in _DANGEROUS_MODULES, f"禁止导入 {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in _DANGEROUS_MODULES

    # 3. 无 os.system/os.popen 属性访问,无顶层 exec/eval 调用
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert not (node.value.id == "os" and node.attr in ("system", "popen", "execv", "execve")), \
                f"禁止使用 os.{node.attr}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("exec", "eval"), f"禁止调用 {node.func.id}"


@pytest.mark.asyncio
async def test_export_trae_skill(client):
    """trae_skill 格式返回 JSON,含 name/description/steps"""
    resp = await client.post(
        "/api/export",
        json={"workflow": _sample_workflow("技能工作流"), "format": "trae_skill"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "trae_skill"
    assert data["content_type"] == "application/json"
    assert data["filename"] == "flowgenie_skill.json"
    parsed = json.loads(data["content"])
    assert parsed["name"] == "flowgenie_workflow"
    assert parsed["description"] == "技能工作流"
    assert isinstance(parsed["steps"], list) and len(parsed["steps"]) == 2


@pytest.mark.asyncio
async def test_export_json_format(client):
    """json 格式返回通用 JSON,含 exported_by 与 version"""
    resp = await client.post(
        "/api/export",
        json={"workflow": _sample_workflow(), "format": "json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "json"
    assert data["filename"] == "flowgenie_workflow.json"
    parsed = json.loads(data["content"])
    assert parsed["exported_by"] == "FlowGenie"
    assert parsed["version"] == "1.0.0"
    assert len(parsed["steps"]) == 2


@pytest.mark.asyncio
async def test_export_unknown_format_rejected(client):
    """未知格式返回 400"""
    resp = await client.post(
        "/api/export",
        json={"workflow": _sample_workflow(), "format": "unknown_fmt"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_python_script_filename_sanitized(client):
    """文件名从 summary 派生并做安全化(特殊字符替换为 _,中文保留)"""
    wf = _sample_workflow(summary="我的工作流/测试*名称")
    resp = await client.post(
        "/api/export",
        json={"workflow": wf, "format": "python_script"},
    )
    assert resp.status_code == 200
    filename = resp.json()["filename"]
    assert filename.endswith(".py")
    # / 与 * 应被替换,不出现在文件名中
    assert "/" not in filename and "*" not in filename
    assert "我的工作流" in filename  # 中文保留
