"""Routers package for xianyu-super-butler API."""
from routers.auth import router as auth_router
from routers.cookies import router as cookies_router
from routers.items import router as items_router
from routers.keywords import router as keywords_router
from routers.orders import router as orders_router
from routers.cards import router as cards_router
from routers.delivery import router as delivery_router
from routers.admin import router as admin_router
from routers.notifications import router as notifications_router
from routers.schedules import router as schedules_router
from routers.system import router as system_router
from routers.login_methods import router as login_methods_router

ALL_ROUTERS = [
    auth_router,
    cookies_router,
    items_router,
    keywords_router,
    orders_router,
    cards_router,
    delivery_router,
    admin_router,
    notifications_router,
    schedules_router,
    system_router,
    login_methods_router,
]
