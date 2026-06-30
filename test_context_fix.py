"""验证变量插值修复：支持带空格的 {{ step.field }}"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from engine.context import ExecutionContext

ctx = ExecutionContext()
ctx.step_results = {"s1": {"output": {"count": 50, "title": "hello"}}}

# 1. 无空格（原有功能）
r1 = ctx.resolve_variables("{{s1.count}}")
print(f"1. 无空格 {{s1.count}}: {r1} (期望 50)")

# 2. 带空格（新增支持）
r2 = ctx.resolve_variables("{{ s1.count }}")
print(f"2. 带空格 {{ s1.count }}: {r2} (期望 50)")

# 3. 带空格 + default
r3 = ctx.resolve_variables("{{ s1.missing | default: 'N/A' }}")
print(f"3. 带空格+default: {r3} (期望 N/A)")

# 4. 无空格 + default（原有功能）
r4 = ctx.resolve_variables("{{s1.missing|default:'N/A'}}")
print(f"4. 无空格+default: {r4} (期望 N/A)")

# 5. 未找到变量返回空字符串
r5 = ctx.resolve_variables("{{s1.missing}}")
print(f"5. 未找到变量: {repr(r5)} (期望 '')")

# 6. 字符串内嵌变量（带空格）
r6 = ctx.resolve_variables("结果: {{ s1.title }}!")
print(f"6. 内嵌变量带空格: {r6} (期望 '结果: hello!')")

# 7. 整个字符串是单个变量引用（带空格），返回原始类型
r7 = ctx.resolve_variables("{{ s1.count }}")
print(f"7. 单变量带空格类型: {type(r7).__name__} = {r7} (期望 int = 50)")

print("\n✅ 全部验证通过" if all([r1==50, r2==50, r3=="N/A", r4=="N/A", r5=="", r6=="结果: hello!", r7==50]) else "\n❌ 有失败项")
