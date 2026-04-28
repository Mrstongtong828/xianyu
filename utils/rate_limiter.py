import time
from typing import Dict, Tuple
from fastapi import Request, HTTPException, status

_limit_store: Dict[str, Tuple[int, int]] = {}

MAX_REQUESTS = 5
WINDOW_SECONDS = 60
CLEANUP_INTERVAL = 300
_last_cleanup = time.time()


def _cleanup():
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    expired = [ip for ip, (_, ts) in _limit_store.items() if now - ts > WINDOW_SECONDS]
    for ip in expired:
        _limit_store.pop(ip, None)


def rate_limit(
    max_requests: int = MAX_REQUESTS,
    window_seconds: int = WINDOW_SECONDS,
    key_func=None,
):
    async def limiter(request: Request):
        _cleanup()
        if key_func:
            key = key_func(request)
        else:
            forwarded = request.headers.get('X-Forwarded-For')
            key = forwarded.split(',')[0].strip() if forwarded else (request.client.host if request.client else 'unknown')

        now = time.time()
        count, timestamp = _limit_store.get(key, (0, now))

        if now - timestamp > window_seconds:
            count = 0
            timestamp = now

        if count >= max_requests:
            retry_after = int(timestamp + window_seconds - now)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请在 {max(retry_after, 1)} 秒后重试",
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        _limit_store[key] = (count + 1, timestamp)

    return limiter
