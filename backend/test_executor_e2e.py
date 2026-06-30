"""端到端验证执行引擎：http_request → file_write"""
import asyncio
import sys
import os
import json

# 添加 backend 到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.executor import executor
from tools import TOOL_EXECUTORS

# 注册所有工具执行器
for tool_name, tool_func in TOOL_EXECUTORS.items():
    executor.register_executor(tool_name, tool_func)


async def main():
    # 构造一个简单工作流：HTTP 请求获取 JSON → 写入文件
    steps = [
        {
            "id": "step_1",
            "name": "获取测试数据",
            "description": "调用公开 API 获取 JSON 数据",
            "tool": "http_request",
            "params": {
                "url": "https://httpbin.org/json",
                "method": "GET",
            },
        },
        {
            "id": "step_2",
            "name": "保存结果到文件",
            "description": "将上一步输出写入本地文件",
            "tool": "file_write",
            "params": {
                "path": "./data/test_run_output.json",
                "format": "json",
                "content": "{{step_1.body}}",  # 变量插值：引用 step_1 的 body 输出
            },
        },
    ]
    edges = [
        {"from": "step_1", "to": "step_2"},
    ]

    print("=" * 60)
    print("开始执行工作流：http_request → file_write")
    print("=" * 60)

    result = await executor.execute(steps=steps, edges=edges, trigger_data=None)

    print(f"\n【总状态】{result['status']}")
    print(f"【总耗时】{result['total_time_ms']} ms\n")

    for step_id, step_result in result["steps_result"].items():
        print(f"--- 步骤 {step_id} ---")
        print(f"  状态: {step_result['status']}")
        print(f"  耗时: {step_result.get('time_ms', 0)} ms")
        if step_result.get("error"):
            print(f"  错误: {step_result['error']}")
        else:
            output = step_result["output"]
            output_str = json.dumps(output, ensure_ascii=False, default=str)
            if len(output_str) > 300:
                output_str = output_str[:300] + "...(截断)"
            print(f"  输出: {output_str}")
        print()

    # 验证文件是否实际写入
    output_path = "./data/test_run_output.json"
    if os.path.exists(output_path):
        print(f"✅ 文件已写入: {output_path} (大小: {os.path.getsize(output_path)} bytes)")
        with open(output_path, "r", encoding="utf-8") as f:
            print(f"   文件内容预览: {f.read()[:200]}")
    else:
        print(f"❌ 文件未写入: {output_path}")

    # 断言
    assert result["status"] == "success", f"工作流应成功，实际: {result['status']}"
    assert "step_1" in result["steps_result"]
    assert "step_2" in result["steps_result"]
    assert result["steps_result"]["step_1"]["status"] == "success"
    assert result["steps_result"]["step_2"]["status"] == "success"
    assert os.path.exists(output_path)
    print("\n🎉 端到端验证通过！执行引擎工作正常。")


if __name__ == "__main__":
    asyncio.run(main())
