"""延时等待工具 - 暂停工作流执行"""
import asyncio


async def execute(params: dict, context) -> dict:
    """
    延时等待
    :param params: {duration, unit="seconds"}
    :return: {waited_seconds, message}
    """
    duration = params.get("duration", 0)
    unit = params.get("unit", "seconds")

    # 数值容错
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0.0

    if duration < 0:
        duration = 0.0

    # 换算为秒
    if unit == "minutes":
        seconds = duration * 60
    elif unit == "hours":
        seconds = duration * 3600
    else:  # seconds 或未知值
        seconds = duration

    # 限制最大等待时间(避免无限等待,1 小时上限)
    seconds = min(seconds, 3600)

    if seconds > 0:
        await asyncio.sleep(seconds)

    waited = int(seconds)
    return {
        "waited_seconds": waited,
        "message": f"已等待 {waited} 秒",
    }
