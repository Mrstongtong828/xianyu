"""
Xianyu Super Butler - 主应用入口
精简版：只负责 FastAPI 初始化、中间件、lifespan、路由注册
具体业务逻辑在 routers/ 目录下各模块中
"""
import os
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from loguru import logger

from shared import db_manager, CAPTCHA_ROUTER_AVAILABLE, setup_file_logging, serve_frontend, API_PREFIXES

# 刮刮乐路由（条件导入）
if CAPTCHA_ROUTER_AVAILABLE:
    from shared import captcha_router


# ============ Lifespan ============

_cleanup_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时创建后台任务，关闭时取消"""
    global _cleanup_task
    async def _periodic_cleanup():
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时清理一次
                db_manager.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理过期session失败: {e}")
    _cleanup_task = asyncio.create_task(_periodic_cleanup())
    logger.info("Session过期清理后台任务已启动")
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass


# ============ App 创建 ============

app = FastAPI(
    title="Xianyu Auto Reply API",
    version="1.0.0",
    description="闲鱼自动回复系统API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


# ============ CORS 中间件 ============

_cors_origins_env = os.getenv('CORS_ORIGINS', '')
if _cors_origins_env:
    cors_origins = [o.strip() for o in _cors_origins_env.split(',') if o.strip()]
else:
    cors_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 请求日志中间件 ============

_STATIC_PATHS = {'/static', '/assets', '/docs', '/openapi.json', '/favicon.ico', '/redoc'}

@app.middleware("http")
async def log_requests(request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in _STATIC_PATHS):
        return await call_next(request)
    start_time = time.time()
    logger.info(f"🌐 API请求: {request.method} {path}")
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"✅ API响应: {request.method} {path} - {response.status_code} ({process_time:.3f}s)")
    return response


# ============ 静态文件 ============

# 初始化文件日志收集器
setup_file_logging()
logger.info("Web服务器启动，文件日志收集器已初始化")

static_dir = os.path.join(os.path.dirname(__file__), 'static')
os.makedirs(static_dir, exist_ok=True)
app.mount('/static', StaticFiles(directory=static_dir), name='static')

assets_dir = os.path.join(static_dir, 'assets')
os.makedirs(assets_dir, exist_ok=True)
app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')

uploads_dir = os.path.join(static_dir, 'uploads', 'images')
os.makedirs(uploads_dir, exist_ok=True)


# ============ 路由注册 ============

from routers import ALL_ROUTERS
for router in ALL_ROUTERS:
    app.include_router(router)

# 刮刮乐远程控制路由
if CAPTCHA_ROUTER_AVAILABLE:
    app.include_router(captcha_router)
    logger.info("✅ 已注册刮刮乐远程控制路由: /api/captcha")
else:
    logger.warning("⚠️ 刮刮乐远程控制路由未注册")


# ============ Catch-all 路由 ============
# Catch-all 路由：处理所有未匹配的 GET 请求，用于前端 SPA

@app.get('/{path:path}', response_class=HTMLResponse)
async def catch_all_route(path: str):
    """Catch-all 路由：处理所有未匹配的 GET 请求"""
    full_path = f'/{path}'
    for prefix in API_PREFIXES:
        if full_path.startswith(prefix):
            raise HTTPException(status_code=404, detail="Not Found")
    return await serve_frontend()


# 移除自动启动，由Start.py或手动启动
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8080)
