"""场景7：定时网页监控 + 企业微信告警
工作流：定时触发 → 网页抓取 → 条件判断 → 企业微信推送
"""


def get_template() -> dict:
    """返回网页监控告警的预定义工作流模板"""
    return {
        "scenario": "监控告警",
        "summary": "每 30 分钟抓取指定网页，命中关键词时通过企业微信推送告警",
        "steps": [
            {
                "id": "step_1",
                "name": "定时触发",
                "description": "每 30 分钟触发一次监控",
                "tool": "schedule_trigger",
                "params": {
                    "cron": "*/30 * * * *",
                    "timezone": "Asia/Shanghai",
                },
            },
            {
                "id": "step_2",
                "name": "抓取网页内容",
                "description": "抓取目标页面并提取关注字段",
                "tool": "web_scraper",
                "params": {
                    "url": "https://example.com",
                    "selector": "article",
                    "fields": ["title", "content"],
                },
            },
            {
                "id": "step_3",
                "name": "关键词判断",
                "description": "判断抓取内容是否包含告警关键词",
                "tool": "if_else",
                "params": {
                    "field": "{{step_2.items}}",
                    "operator": "contain",
                    "value": "关键词",
                },
            },
            {
                "id": "step_4",
                "name": "企业微信告警",
                "description": "命中关键词时推送到企业微信机器人",
                "tool": "send_wechat",
                "params": {
                    "content": "{{step_2.items}}",
                    "msg_type": "markdown",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4", "condition": "true"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["网页监控", "监控", "告警", "关键词", "企业微信", "wechat", "定时抓取", "页面变化"]
