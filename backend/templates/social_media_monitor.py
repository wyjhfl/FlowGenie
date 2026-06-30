"""场景12：社媒舆情监控
工作流：HTTP 抓取社媒数据 → LLM 情感分类 → switch_branch 负面告警 → 多渠道推送
"""


def get_template() -> dict:
    """返回社媒舆情监控的预定义工作流模板"""
    return {
        "scenario": "监控告警",
        "summary": "抓取社交媒体数据，用 LLM 进行情感分类，负面舆情通过 switch_branch 路由到多渠道告警",
        "steps": [
            {
                "id": "step_1",
                "name": "抓取社媒数据",
                "description": "通过 API 抓取社交媒体提及",
                "tool": "http_request",
                "params": {
                    "url": "https://api.example.com/mentions",
                    "method": "GET",
                    "headers": {},
                },
            },
            {
                "id": "step_2",
                "name": "情感分类",
                "description": "对社媒内容进行情感分析",
                "tool": "llm_classify",
                "params": {
                    "text": "{{step_1.body}}",
                    "task": "sentiment",
                },
            },
            {
                "id": "step_3",
                "name": "分支路由",
                "description": "按情感分类结果路由：负面走告警，其他走记录",
                "tool": "switch_branch",
                "params": {
                    "field": "{{step_2.category}}",
                    "cases": ["正面", "负面", "中性"],
                },
            },
            {
                "id": "step_4",
                "name": "负面告警推送",
                "description": "负面舆情通过 Telegram 与微信告警",
                "tool": "send_telegram",
                "params": {
                    "chat_id": "alert_chat_id",
                    "text": "⚠️ 负面舆情告警\n分类: {{step_2.category}}\n原因: {{step_2.reason}}\n原文: {{step_1.body}}",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4", "condition": "负面"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["社媒", "监控", "舆情", "social", "monitor", "品牌监控", "口碑", "情感分析", "舆情监控"]
