"""场景2：销售数据报表生成
工作流：定时触发 → 数据库查询销售数据 → LLM 分析 → 邮件发送
"""


def get_template() -> dict:
    """返回销售数据报表的预定义工作流模板"""
    return {
        "scenario": "数据处理",
        "summary": "每周一从数据库导出销售数据，经 LLM 分析后发送邮件给团队",
        "steps": [
            {
                "id": "step_1",
                "name": "定时触发",
                "description": "每周一早上 9 点触发",
                "tool": "schedule_trigger",
                "params": {
                    "cron": "0 9 * * 1",
                    "timezone": "Asia/Shanghai",
                },
            },
            {
                "id": "step_2",
                "name": "查询销售数据",
                "description": "从数据库查询上周销售数据",
                "tool": "database_query",
                "params": {
                    "connection": "sqlite:///sales.db",
                    "query": "SELECT product, SUM(amount) as total, COUNT(*) as orders FROM sales WHERE date >= NOW() - INTERVAL '7 days' GROUP BY product ORDER BY total DESC",
                },
            },
            {
                "id": "step_3",
                "name": "AI 分析数据",
                "description": "用 LLM 分析销售数据趋势并给出洞察",
                "tool": "llm_analysis",
                "params": {
                    "data": "{{step_2.rows}}",
                    "task": "分析上周销售数据，找出销量最佳的产品和整体趋势",
                },
            },
            {
                "id": "step_4",
                "name": "发送邮件",
                "description": "把分析报告邮件发给团队",
                "tool": "send_email",
                "params": {
                    "to": "team@example.com",
                    "subject": "上周销售数据报表",
                    "content": "{{step_3.analysis}}",
                    "content_type": "plain",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["销售", "报表", "数据", "数据库", "sales", "report", "图表", "邮件", "每周", "导出"]
