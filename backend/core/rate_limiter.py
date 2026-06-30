"""内存令牌桶限流器 - 防止 webhook 滥用

策略:每 key 在 window_seconds 内最多 max_requests 次,超限返回 429。
不引入 Redis,适合单实例部署。多实例需替换为 Redis 实现。
"""
import time
from collections import defaultdict
from threading import Lock

# 默认:每 30 秒最多 10 次
_DEFAULT_WINDOW = 30
_DEFAULT_MAX = 10


class TokenBucketLimiter:
    """滑动窗口限流器(线程安全)

    每个独立的 key(如 webhook_id)维护一个窗口,
    超过 max_requests/window_seconds 则拒绝。
    """

    def __init__(self, window_seconds: int = _DEFAULT_WINDOW, max_requests: int = _DEFAULT_MAX):
        self.window = window_seconds
        self.max = max_requests
        # {key: [timestamp1, timestamp2, ...]}
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        """检查 key 是否允许通过。允许则记录本次访问,拒绝则返回 False。"""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[key]
            # 清理过期时间戳
            cutoff = now - self.window
            self._buckets[key] = [t for t in bucket if t > cutoff]
            bucket = self._buckets[key]
            if len(bucket) >= self.max:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str | None = None):
        """重置指定 key 或全部。测试用。"""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


# 全局单例:webhook 限流(每 webhook_id 30s/10 次)
webhook_limiter = TokenBucketLimiter(window_seconds=30, max_requests=10)
