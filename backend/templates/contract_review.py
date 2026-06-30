"""场景：合同审核
工作流：文件读取 → LLM 分析 → 文件写入
"""


def get_template() -> dict:
    """返回合同审核的预定义工作流模板"""
    return {
        "scenario": "文档处理",
        "summary": "读取合同文档，AI 分析条款和风险，生成审核报告",
        "steps": [
            {
                "id": "step_1",
                "name": "读取合同",
                "tool": "file_read",
                "params": {
                    "path": "contract.txt",
                    "format": "text"
                },
                "description": "读取合同文档内容"
            },
            {
                "id": "step_2",
                "name": "AI分析",
                "tool": "llm_analysis",
                "params": {
                    "data": "{{step_1.content}}",
                    "task": "分析合同条款，识别以下风险点：1. 付款条件风险 2. 违约责任 3. 知识产权归属 4. 保密条款 5. 终止条件。输出结构化分析报告。"
                },
                "description": "AI 分析合同条款和风险"
            },
            {
                "id": "step_3",
                "name": "保存报告",
                "tool": "file_write",
                "params": {
                    "path": "contract_review_report.txt",
                    "content": "{{step_2.analysis}}",
                    "format": "text"
                },
                "description": "保存审核报告到文件"
            }
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"}
        ]
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["合同", "审核", "contract", "review", "条款", "风险"]
