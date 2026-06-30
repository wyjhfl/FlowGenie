"""场景1：每日新闻摘要推送
工作流：定时触发 → 网页抓取新闻 → LLM 摘要 → 微信推送
"""


def get_template() -> dict:
    """返回新闻摘要推送的预定义工作流模板"""
    return {
        "scenario": "信息收集",
        "summary": "每天定时抓取科技新闻，生成摘要并推送到指定渠道",
        "steps": [
            {
                "id": "step_1",
                "name": "定时触发",
                "description": "每天早上 8 点触发工作流",
                "tool": "schedule_trigger",
                "params": {
                    "cron": "0 8 * * *",
                    "timezone": "Asia/Shanghai",
                },
            },
            {
                "id": "step_2",
                "name": "抓取科技新闻",
                "description": "从新闻网站抓取最新科技资讯",
                "tool": "web_scraper",
                "params": {
                    "url": "https://news.ycombinator.com",
                    "selector": "a.titlelink",
                    "fields": ["title", "href"],
                },
            },
            {
                "id": "step_3",
                "name": "生成新闻摘要",
                "description": "用 LLM 把抓取的新闻生成中文摘要",
                "tool": "llm_summary",
                "params": {
                    "text": "{{step_2.items}}",
                    "max_length": 800,
                    "language": "zh",
                },
            },
            {
                "id": "step_4",
                "name": "推送摘要",
                "description": "把摘要推送到企业微信",
                "tool": "send_wechat",
                "params": {
                    "content": "{{step_3.summary}}",
                    "msg_type": "markdown",
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
    return ["新闻", "摘要", "抓取", "rss", "news", "summary", "每天", "推送", "早报"]
