"""并发执行限制 - 信号量控制同时执行的工作流数量"""
import asyncio
import os

# 默认并发上限 5（可通过环境变量 WORKFLOW_MAX_CONCURRENT 调整）
MAX_CONCURRENT = int(os.getenv("WORKFLOW_MAX_CONCURRENT", "5"))

# 全局信号量
_semaphore: asyncio.Semaphore | None = None


def get_semaphore() -> asyncio.Semaphore:
    """获取全局信号量（懒初始化，确保在事件循环内创建）"""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


async def acquire_execution_slot():
    """获取执行槽位（信号量 acquire）"""
    await get_semaphore().acquire()


def release_execution_slot():
    """释放执行槽位（信号量 release）"""
    get_semaphore().release()
