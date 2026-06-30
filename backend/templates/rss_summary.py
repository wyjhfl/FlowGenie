"""场景4：RSS 订阅聚合 + AI 摘要 + 邮件推送
工作流：RSS 读取 → LLM 摘要 → 邮件推送
"""


def get_template() -> dict:
    """返回 RSS 订阅聚合摘要推送的预定义工作流模板"""
    return {
        "scenario": "信息收集",
        "summary": "聚合 RSS 订阅源，用 LLM 生成摘要并通过邮件推送给订阅者",
        "steps": [
            {
                "id": "step_1",
                "name": "读取 RSS 订阅",
                "description": "从 RSS 源拉取最新 10 篇文章",
                "tool": "rss_reader",
                "params": {
                    "feed_url": "https://feeds.example.com/rss",
                    "limit": 10,
                },
            },
            {
                "id": "step_2",
                "name": "生成摘要",
                "description": "用 LLM 把 RSS 文章聚合生成中文摘要",
                "tool": "llm_summary",
                "params": {
                    "text": "{{step_1.items}}",
                    "max_length": 500,
                    "language": "zh",
                },
            },
            {
                "id": "step_3",
                "name": "邮件推送",
                "description": "把摘要通过邮件发送给订阅者",
                "tool": "send_email",
                "params": {
                    "to": "subscriber@example.com",
                    "subject": "今日 RSS 文章摘要",
                    "content": "{{step_2.summary}}",
                    "content_type": "plain",
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
    return ["rss", "订阅", "聚合", "feed", "邮件摘要", "资讯摘要", "newsletter"]
