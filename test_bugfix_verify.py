"""验证修复后的模板工作流：解析 + 执行（用 file_write 替换推送步骤避免需要真实凭证）"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
import httpx
import json

BASE = "http://localhost:8000"

# 1. 测试新闻摘要模板解析
print("=== 测试1: 新闻摘要模板解析 ===")
r = httpx.post(f"{BASE}/api/parse", json={"requirement": "每天早上抓取科技新闻生成摘要推送"}, timeout=30)
print(f"POST /api/parse -> {r.status_code}")
result = r.json()
print(f"来源: {result['source']}, 场景: {result['scenario']}")
print(f"步骤数: {len(result['steps'])}")
for s in result["steps"]:
    print(f"  - {s['id']}: {s['name']} ({s['tool']})")
    print(f"    params keys: {list(s.get('params', {}).keys())}")

# 2. 验证模板中所有工具都有实现
print("\n=== 测试2: 验证模板工具均有实现 ===")
# 获取已注册工具
r = httpx.get(f"{BASE}/openapi.json")
# 直接检查 execute 路由可用

# 3. 执行一个简化工作流（http_request → llm_summary → file_write）
# 避免需要真实 webhook/SMTP 凭证
print("\n=== 测试3: 执行简化工作流 (http → llm_summary → file_write) ===")
payload = {
    "steps": [
        {
            "id": "step_1",
            "name": "获取数据",
            "tool": "http_request",
            "params": {"url": "https://httpbin.org/json", "method": "GET"},
        },
        {
            "id": "step_2",
            "name": "生成摘要",
            "tool": "llm_summary",
            "params": {
                "text": "{{step_1.body}}",
                "max_length": 200,
                "language": "zh",
            },
        },
        {
            "id": "step_3",
            "name": "保存结果",
            "tool": "file_write",
            "params": {
                "path": "./backend/data/bugfix_verify.json",
                "format": "json",
                "content": "{{step_2}}",
            },
        },
    ],
    "edges": [
        {"from": "step_1", "to": "step_2"},
        {"from": "step_2", "to": "step_3"},
    ],
    "trigger_data": None,
}
r = httpx.post(f"{BASE}/api/workflows/run", json=payload, timeout=120)
print(f"POST /api/workflows/run -> {r.status_code}")
run_result = r.json()
print(f"总状态: {run_result['status']}")
print(f"总耗时: {run_result['total_time_ms']} ms")
for sid, sr in run_result["steps_result"].items():
    print(f"  {sid}: {sr['status']} ({sr.get('time_ms', 0)} ms)")
    if sr.get("error"):
        print(f"    错误: {sr['error'][:200]}")
    elif sr["status"] == "success":
        out = sr["output"]
        out_str = json.dumps(out, ensure_ascii=False, default=str)
        print(f"    输出预览: {out_str[:150]}")

# 4. 验证文件写入
output_path = "./backend/data/bugfix_verify.json"
if os.path.exists(output_path):
    print(f"\n✅ 文件已写入: {output_path} ({os.path.getsize(output_path)} bytes)")
else:
    print(f"\n❌ 文件未写入: {output_path}")

# 5. 验证所有模板工具都有执行器
print("\n=== 测试4: 验证模板工具执行器覆盖 ===")
# 新闻模板工具: schedule_trigger, web_scraper, llm_summary, send_wechat
# 销售模板工具: schedule_trigger, database_query, llm_analysis, send_email
# Review模板工具: webhook_trigger, http_request, llm_review, send_slack
template_tools = [
    "schedule_trigger", "web_scraper", "llm_summary", "send_wechat",
    "database_query", "llm_analysis", "send_email",
    "webhook_trigger", "http_request", "llm_review", "send_slack",
    "manual_trigger", "file_write",
]
# 通过执行一个引用不存在工具的工作流来测试
for tool in template_tools:
    test_payload = {
        "steps": [{"id": "t1", "name": "test", "tool": tool, "params": {}}],
        "edges": [],
        "trigger_data": None,
    }
    r = httpx.post(f"{BASE}/api/workflows/run", json=test_payload, timeout=10)
    result = r.json()
    sr = result["steps_result"].get("t1", {})
    status = sr.get("status")
    # 触发器类工具应该是 skipped，其他工具应该是因为参数缺失而 failed（不是"未实现"）
    if tool in ("schedule_trigger", "webhook_trigger", "manual_trigger"):
        if status == "skipped":
            print(f"  ✅ {tool}: skipped (触发器正确跳过)")
        else:
            print(f"  ❌ {tool}: 期望 skipped，实际 {status}")
    else:
        error = sr.get("error", "")
        if "未实现" in error:
            print(f"  ❌ {tool}: 未实现执行逻辑!")
        else:
            print(f"  ✅ {tool}: 已实现 (状态: {status}, 错误: {error[:60] if error else '无'})")

print("\n🎉 验证完成")
