"""检查工作流执行结果 - 用法: python inspect_run.py <result_file.json>"""
import json
import sys


def main(path: str):
    d = json.load(open(path, "r", encoding="utf-8-sig"))
    print("STATUS:", d.get("status"))
    print("TOTAL_MS:", d.get("total_time_ms"))
    print("---STEPS---")
    sr = d.get("steps_result", {})
    if isinstance(sr, dict):
        for k, v in sr.items():
            if isinstance(v, dict):
                status = v.get("status", "unknown")
                keys = list(v.keys())
                err = v.get("error", "")
                line = f"  {k}: status={status} keys={keys}"
                if err:
                    line += f" error={err[:150]}"
                print(line)
                # 打印部分输出字段值(截断)
                for fk in ("summary", "analysis", "translation", "category", "matched_case", "items", "content", "rendered"):
                    if fk in v:
                        val = v.get(fk)
                        sval = str(val)
                        print(f"      {fk}: {sval[:200]}")
            else:
                print(f"  {k}: {v}")
    print("---LOGS(tail 8)---")
    for l in d.get("logs", [])[-8:]:
        print(" ", l)
    print("---WARNINGS---")
    for w in d.get("warnings", []):
        print(" ", w)


if __name__ == "__main__":
    main(sys.argv[1])
