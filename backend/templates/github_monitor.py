"""场景5：GitHub Issue 监控 + Slack 推送
工作流：定时触发 → GitHub API 查询 Issue → 条件判断 → Slack 推送
"""


def get_template() -> dict:
    """返回 GitHub Issue 监控的预定义工作流模板"""
    return {
        "scenario": "运维自动化",
        "summary": "每天定时检查 GitHub 仓库的新 Issue，有新 Issue 时推送到 Slack 频道",
        "steps": [
            {
                "id": "step_1",
                "name": "定时触发",
                "description": "每天早上 9 点触发检查",
                "tool": "schedule_trigger",
                "params": {
                    "cron": "0 9 * * *",
                    "timezone": "Asia/Shanghai",
                },
            },
            {
                "id": "step_2",
                "name": "查询 Open Issue",
                "description": "通过 GitHub API 获取仓库最新的 open 状态 Issue",
                "tool": "github_api",
                "params": {
                    "endpoint": "repos/{owner}/{repo}/issues",
                    "owner": "owner",
                    "repo": "repo",
                    "method": "GET",
                    "params": {"state": "open", "sort": "created", "direction": "desc"},
                },
            },
            {
                "id": "step_3",
                "name": "判断是否有 Issue",
                "description": "当返回数据非空时才推送通知",
                "tool": "if_else",
                "params": {
                    "field": "{{step_2.body}}",
                    "operator": "is_not_empty",
                    "value": "",
                },
            },
            {
                "id": "step_4",
                "name": "Slack 推送",
                "description": "把新 Issue 列表推送到 Slack 频道",
                "tool": "send_slack",
                "params": {
                    "text": "{{step_2.body}}",
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
    return ["github", "issue", "仓库", "slack", "监控", "open issue", "bug 跟踪"]
