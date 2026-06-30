"""场景11：每日新闻简报
工作流：多源新闻抓取 → LLM 聚合摘要 → LLM 翻译 → 邮件/飞书推送
"""


def get_template() -> dict:
    """返回每日新闻简报的预定义工作流模板"""
    return {
        "scenario": "信息收集",
        "summary": "抓取多个新闻源，用 LLM 生成聚合摘要并翻译为目标语言，通过邮件或飞书推送每日简报",
        "steps": [
            {
                "id": "step_1",
                "name": "抓取科技新闻",
                "description": "从 Hacker News 抓取最新科技资讯",
                "tool": "web_scraper",
                "params": {
                    "url": "https://news.ycombinator.com/",
                    "selector": "a.titlelink",
                    "fields": ["title"],
                },
            },
            {
                "id": "step_2",
                "name": "抓取综合新闻",
                "description": "从 BBC 抓取综合新闻",
                "tool": "web_scraper",
                "params": {
                    "url": "https://www.bbc.com/news",
                    "selector": "h3",
                    "fields": ["title"],
                },
            },
            {
                "id": "step_3",
                "name": "生成聚合摘要",
                "description": "把两个来源的新闻合并并用 LLM 生成中文摘要",
                "tool": "llm_summary",
                "params": {
                    "text": "{{step_1.items}}\n\n{{step_2.items}}",
                    "max_length": 800,
                    "language": "zh",
                },
            },
            {
                "id": "step_4",
                "name": "翻译为英文",
                "description": "把中文摘要翻译为英文",
                "tool": "llm_translate",
                "params": {
                    "text": "{{step_3.summary}}",
                    "source_lang": "zh",
                    "target_lang": "en",
                },
            },
            {
                "id": "step_5",
                "name": "邮件推送简报",
                "description": "把中英文摘要通过邮件发送",
                "tool": "send_email",
                "params": {
                    "to": "subscriber@example.com",
                    "subject": "每日新闻简报",
                    "content": "中文摘要:\n{{step_3.summary}}\n\nEnglish Briefing:\n{{step_4.translation}}",
                    "content_type": "plain",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_3"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"},
            {"from": "step_4", "to": "step_5"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["新闻", "简报", "每日", "news", "briefing", "日报", "晨报", "每日简报", "新闻摘要"]
