"""场景6：定时 AI 生成内容 + Telegram 推送
工作流：定时触发 → LLM 生成内容 → Telegram 推送
"""


def get_template() -> dict:
    """返回定时 AI 内容生成 Telegram 推送的预定义工作流模板"""
    return {
        "scenario": "内容生成",
        "summary": "每天定时用 LLM 生成 AI 资讯摘要并推送到 Telegram 聊天",
        "steps": [
            {
                "id": "step_1",
                "name": "定时触发",
                "description": "每天早上 8 点触发内容生成",
                "tool": "schedule_trigger",
                "params": {
                    "cron": "0 8 * * *",
                    "timezone": "Asia/Shanghai",
                },
            },
            {
                "id": "step_2",
                "name": "AI 生成内容",
                "description": "用 LLM 生成今日 AI 资讯摘要",
                "tool": "llm_generate",
                "params": {
                    "content_type": "report",
                    "topic": "生成今日 AI 资讯摘要",
                    "tone": "professional",
                    "language": "zh",
                    "length": "约1000字",
                },
            },
            {
                "id": "step_3",
                "name": "Telegram 推送",
                "description": "把生成的内容推送到 Telegram 聊天",
                "tool": "send_telegram",
                "params": {
                    "chat_id": "123456789",
                    "text": "{{step_2.content}}",
                    "parse_mode": "text",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["telegram", "tg", "电报", "ai 资讯", "内容生成", "定时推送", "bot"]
