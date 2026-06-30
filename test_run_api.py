"""验证后端 /api/workflows/run 端点（放在 backend 外避免触发 reload）"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
import httpx

BASE = "http://localhost:8000"

# 1. 健康检查
print("=== 健康检查 ===")
r = httpx.get(f"{BASE}/api/health")
print(f"GET /api/health -> {r.status_code}: {r.text}")

# 2. 执行工作流
print("\n=== 执行工作流 ===")
payload = {
    "steps": [
        {
            "id": "s1",
            "name": "获取测试数据",
            "tool": "http_request",
            "params": {"url": "https://httpbin.org/json", "method": "GET"},
        },
        {
            "id": "s2",
            "name": "保存到文件",
            "tool": "file_write",
            "params": {
                "path": "./backend/data/verify_run.json",
                "format": "json",
                "content": "{{s1.body}}",
            },
        },
    ],
    "edges": [{"from": "s1", "to": "s2"}],
    "trigger_data": None,
}
r = httpx.post(f"{BASE}/api/workflows/run", json=payload, timeout=60)
print(f"POST /api/workflows/run -> {r.status_code}")
result = r.json()
print(f"总状态: {result['status']}")
print(f"总耗时: {result['total_time_ms']} ms")
for sid, sr in result["steps_result"].items():
    print(f"  {sid}: {sr['status']} ({sr.get('time_ms', 0)} ms)")
    if sr.get("error"):
        print(f"    错误: {sr['error']}")

# 3. 验证 OpenAPI 文档中 execute 路由已注册
print("\n=== 验证路由注册 ===")
r = httpx.get(f"{BASE}/openapi.json")
paths = r.json().get("paths", {})
run_path = "/api/workflows/run"
if run_path in paths:
    print(f"✅ 路由 {run_path} 已注册: {list(paths[run_path].keys())}")
else:
    print(f"❌ 路由 {run_path} 未注册")
    print("已注册的 /api/workflows 路径:", [p for p in paths if "workflow" in p])

print("\n🎉 验证完成")
