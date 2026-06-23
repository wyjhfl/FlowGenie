"""场景2：销售数据报表生成
工作流：定时触发 → 数据库查询销售数据 → 数据清洗 → 图表生成 + 报表生成 → 邮件发送
"""
from core.tool_registry import get_tool


def get_template() -> dict:
    """返回销售数据报表的预定义工作流模板"""
    return {
        "scenario": "数据处理",
        "summary": "每周一从数据库导出销售数据，生成可视化报表并发送邮件给团队",
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
                    "connection": "postgresql://user:pass@host:5432/sales_db",
                    "query": "SELECT product, SUM(amount) as total, COUNT(*) as orders FROM sales WHERE date >= NOW() - INTERVAL '7 days' GROUP BY product ORDER BY total DESC",
                },
            },
            {
                "id": "step_3",
                "name": "清洗数据",
                "description": "去重、格式化数据",
                "tool": "data_cleaner",
                "params": {
                    "rules": ["deduplicate", "trim_whitespace", "fill_null"],
                },
            },
            {
                "id": "step_4",
                "name": "生成图表",
                "description": "生成销售柱状图",
                "tool": "chart_generator",
                "params": {
                    "type": "bar",
                    "title": "上周销售数据报表",
                    "x_field": "product",
                    "y_field": "total",
                },
            },
            {
                "id": "step_5",
                "name": "生成报表",
                "description": "生成 HTML 格式报表",
                "tool": "report_generator",
                "params": {
                    "format": "html",
                    "template": "sales_weekly",
                },
            },
            {
                "id": "step_6",
                "name": "发送邮件",
                "description": "把报表邮件发给团队",
                "tool": "send_email",
                "params": {
                    "to": "team@example.com",
                    "subject": "上周销售数据报表",
                    "smtp_host": "smtp.example.com",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"},
            {"from": "step_4", "to": "step_5"},
            {"from": "step_5", "to": "step_6"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["销售", "报表", "数据", "数据库", "sales", "report", "图表", "邮件", "每周", "导出"]
