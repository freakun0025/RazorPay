from fastapi import FastAPI
from app.api.routes import webhooks

app = FastAPI(title="RazorPay Recovery Engine")

app.include_router(webhooks.router)
