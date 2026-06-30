"""场景13：会议纪要生成
工作流：读取转录文本 → LLM 抽取要点 → LLM 生成摘要 → 写入文件 → 邮件分发
"""


def get_template() -> dict:
    """返回会议纪要生成的预定义工作流模板"""
    return {
        "scenario": "办公自动化",
        "summary": "读取会议转录文本，用 LLM 抽取议题/决策/待办要点，生成摘要并写入文件后邮件分发",
        "steps": [
            {
                "id": "step_1",
                "name": "读取会议转录",
                "description": "读取本地会议转录文本文件",
                "tool": "file_read",
                "params": {
                    "path": "input/meeting_transcript.txt",
                    "format": "text",
                },
            },
            {
                "id": "step_2",
                "name": "抽取要点",
                "description": "从转录中抽取议题、决策、待办事项",
                "tool": "llm_extract",
                "params": {
                    "text": "{{step_1.content}}",
                    "schema": "议题, 决策, 待办, 责任人, 截止日期",
                    "instruction": "请从会议转录中结构化抽取关键信息",
                },
            },
            {
                "id": "step_3",
                "name": "生成纪要摘要",
                "description": "用 LLM 生成会议纪要摘要",
                "tool": "llm_summary",
                "params": {
                    "text": "{{step_2.entities}}",
                    "max_length": 500,
                    "language": "zh",
                },
            },
            {
                "id": "step_4",
                "name": "写入纪要文件",
                "description": "把会议纪要写入 Markdown 文件",
                "tool": "file_write",
                "params": {
                    "path": "output/meeting_minutes.md",
                    "format": "text",
                    "content": "# 会议纪要\n\n## 摘要\n{{step_3.summary}}\n\n## 要点\n{{step_2.entities}}",
                },
            },
            {
                "id": "step_5",
                "name": "邮件分发",
                "description": "把纪要通过邮件发给参会者",
                "tool": "send_email",
                "params": {
                    "to": "team@example.com",
                    "subject": "会议纪要",
                    "content": "{{step_3.summary}}",
                    "content_type": "plain",
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
    return ["会议", "纪要", "minutes", "meeting", "转录", "会议记录", "会议摘要", "meeting minutes"]
