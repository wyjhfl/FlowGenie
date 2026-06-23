"""场景3：代码提交后 Code Review
工作流：Webhook 触发 → GitHub API 获取提交 → LLM Code Review → Slack 推送问题
"""
from core.tool_registry import get_tool


def get_template() -> dict:
    """返回 Code Review 的预定义工作流模板"""
    return {
        "scenario": "运维自动化",
        "summary": "每次代码提交后自动进行 Code Review，把发现的问题推送到 Slack",
        "steps": [
            {
                "id": "step_1",
                "name": "Webhook 触发",
                "description": "GitHub Push 事件触发",
                "tool": "webhook_trigger",
                "params": {
                    "path": "/webhook/github-push",
                    "method": "POST",
                },
            },
            {
                "id": "step_2",
                "name": "获取提交内容",
                "description": "通过 GitHub API 获取本次提交的 diff",
                "tool": "github_api",
                "params": {
                    "endpoint": "/repos/{owner}/{repo}/commits/{sha}",
                    "owner": "your-org",
                    "repo": "your-repo",
                },
            },
            {
                "id": "step_3",
                "name": "AI Code Review",
                "description": "用 LLM 对代码进行 Review",
                "tool": "llm_review",
                "params": {
                    "model": "deepseek-chat",
                    "focus": ["bug", "security", "performance", "style"],
                },
            },
            {
                "id": "step_4",
                "name": "推送 Review 结果",
                "description": "把 Review 发现的问题推送到 Slack",
                "tool": "send_slack",
                "params": {
                    "webhook_url": "https://hooks.slack.com/services/xxx",
                    "channel": "#code-review",
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
    return ["代码", "code review", "review", "提交", "commit", "github", "slack", "审查", "push"]
