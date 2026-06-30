"""检查 parse 结果 - 用法: python inspect_parse.py <file.json>"""
import json
import sys


def main(path: str):
    d = json.load(open(path, "r", encoding="utf-8-sig"))
    print("source:", d.get("source"))
    print("scenario:", d.get("scenario"))
    print("summary:", d.get("summary", "")[:120])
    print("steps_count:", len(d.get("steps", [])))
    steps = d.get("steps", [])
    print("tools:", " -> ".join([s["tool"] for s in steps]))
    edges = d.get("edges", [])
    print("edges:", [(e["from"], e["to"]) for e in edges])
    print("---STEPS---")
    for s in steps:
        params = s.get("params", {})
        pk = list(params.keys())
        print(f"  {s['id']}: tool={s['tool']} params_keys={pk}")
        # 显示部分关键参数值(截断)
        for k in ("path", "text", "data", "field", "cases", "categories", "task", "schema", "input_array", "duration", "unit", "url"):
            if k in params:
                v = params[k]
                sv = str(v)
                print(f"      {k}: {sv[:120]}")


if __name__ == "__main__":
    main(sys.argv[1])
