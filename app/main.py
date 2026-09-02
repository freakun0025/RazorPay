from fastapi import FastAPI
from app.api.middleware.correlation import CorrelationIdMiddleware
from app.api.routes import webhooks, admin, health

from app.utils.logger import setup_logging
setup_logging()

app = FastAPI(title="RazorPay Recovery Engine")
app.add_middleware(CorrelationIdMiddleware)

app.include_router(webhooks.router)
app.include_router(admin.router)

app.include_router(health.router)

