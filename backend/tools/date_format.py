"""日期格式化工具 - 格式化日期/时间,支持时区转换与日期运算"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


async def execute(params: dict, context) -> dict:
    """
    日期格式化
    :param params: {
        datetime: 输入时间(空则用 now),
        input_format: 输入格式(strftime,空则 ISO 解析),
        output_format: 输出格式(strftime),
        timezone: 时区(默认 Asia/Shanghai),
        add_days: 日期运算天数(可为负)
    }
    :return: { formatted, timestamp, iso }
    """
    dt_str = params.get("datetime", "")
    input_format = params.get("input_format", "")
    output_format = params.get("output_format", "%Y-%m-%d %H:%M:%S")
    tz_name = params.get("timezone", "Asia/Shanghai")
    add_days = params.get("add_days")

    # 解析时区
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")

    # 解析输入时间
    if not dt_str:
        dt = datetime.now(tz)
    elif input_format:
        try:
            dt = datetime.strptime(str(dt_str), input_format)
            dt = dt.replace(tzinfo=tz)
        except ValueError as e:
            raise ValueError(f"输入时间无法按格式 {input_format} 解析: {e}")
    else:
        # 尝试 ISO 8601 解析
        try:
            dt_str_normalized = str(dt_str).replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_str_normalized)
            # 转换到目标时区
            dt = dt.astimezone(tz)
        except ValueError:
            # 回退:尝试常见格式
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
                try:
                    dt = datetime.strptime(str(dt_str), fmt).replace(tzinfo=tz)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"无法解析输入时间: {dt_str}")

    # 日期运算
    if add_days is not None and add_days != "":
        try:
            days = int(add_days)
            dt = dt + timedelta(days=days)
        except (TypeError, ValueError):
            pass  # 忽略无效的 add_days

    # 格式化输出
    formatted = dt.strftime(output_format)
    timestamp = int(dt.timestamp())
    iso = dt.isoformat()

    return {
        "formatted": formatted,
        "timestamp": timestamp,
        "iso": iso,
    }
