"""场景15：内容本地化
工作流：读取原文 → LLM 翻译 → 文本模板适配 → 写入译文 → 通知
"""


def get_template() -> dict:
    """返回内容本地化的预定义工作流模板"""
    return {
        "scenario": "内容处理",
        "summary": "读取原始内容，用 LLM 翻译为目标语言，通过模板渲染本地化适配后写入文件并通知",
        "steps": [
            {
                "id": "step_1",
                "name": "读取原文",
                "description": "读取待本地化的原文文件",
                "tool": "file_read",
                "params": {
                    "path": "input/content.md",
                    "format": "text",
                },
            },
            {
                "id": "step_2",
                "name": "翻译内容",
                "description": "把原文翻译为中文",
                "tool": "llm_translate",
                "params": {
                    "text": "{{step_1.content}}",
                    "source_lang": "en",
                    "target_lang": "zh",
                },
            },
            {
                "id": "step_3",
                "name": "本地化模板适配",
                "description": "用模板渲染生成最终本地化文档",
                "tool": "text_template",
                "params": {
                    "template": "# 本地化内容\n\n> 原文: {{original}}\n\n## 译文\n{{translation}}",
                    "variables": {
                        "original": "{{step_1.content}}",
                        "translation": "{{step_2.translation}}",
                    },
                },
            },
            {
                "id": "step_4",
                "name": "写入本地化文件",
                "description": "把本地化内容写入文件",
                "tool": "file_write",
                "params": {
                    "path": "output/localized_content.md",
                    "format": "text",
                    "content": "{{step_3.rendered}}",
                },
            },
            {
                "id": "step_5",
                "name": "Slack 通知",
                "description": "通过 Slack 通知本地化完成",
                "tool": "send_slack",
                "params": {
                    "text": "✅ 内容本地化完成: {{step_4.path}}",
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
    return ["本地化", "翻译", "localization", "多语言", "国际化", "i18n", "内容本地化", "l10n"]
