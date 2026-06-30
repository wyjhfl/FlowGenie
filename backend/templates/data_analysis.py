"""场景8：个人数据分析报告
工作流：文件读取 → 数据转换 → 图表生成 → LLM 分析 → 文件写入
"""


def get_template() -> dict:
    """返回个人数据分析报告的预定义工作流模板"""
    return {
        "scenario": "数据处理",
        "summary": "读取本地销售数据文件，清洗转换后生成图表与趋势分析，输出 Markdown 报告",
        "steps": [
            {
                "id": "step_1",
                "name": "读取数据文件",
                "description": "读取本地 JSON 销售数据文件",
                "tool": "file_read",
                "params": {
                    "path": "data/sales.json",
                    "format": "json",
                },
            },
            {
                "id": "step_2",
                "name": "清洗与转换",
                "description": "对原始数据去重并过滤有效记录",
                "tool": "data_transform",
                "params": {
                    "data": "{{step_1.content}}",
                    "operations": [
                        {"type": "deduplicate", "key": "id"},
                        {"type": "filter", "field": "amount", "operator": "gt", "value": 0},
                    ],
                },
            },
            {
                "id": "step_3",
                "name": "生成数据图表",
                "description": "把清洗后的数据生成表格视图",
                "tool": "chart_generator",
                "params": {
                    "data": "{{step_2.data}}",
                    "chart_type": "table",
                    "title": "销售数据报表",
                },
            },
            {
                "id": "step_4",
                "name": "AI 趋势分析",
                "description": "用 LLM 分析数据趋势并给出洞察",
                "tool": "llm_analysis",
                "params": {
                    "data": "{{step_2.data}}",
                    "task": "分析销售数据趋势，找出增长点和异常波动",
                },
            },
            {
                "id": "step_5",
                "name": "输出报告",
                "description": "把分析结果写入 Markdown 报告文件",
                "tool": "file_write",
                "params": {
                    "path": "data/report.md",
                    "content": "{{step_4.analysis}}",
                    "format": "text",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"},
            {"from": "step_4", "to": "step_5"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["数据分析", "报告", "csv", "清洗", "趋势", "图表", "分析报告", "data analysis"]
