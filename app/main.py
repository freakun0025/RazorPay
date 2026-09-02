from fastapi import FastAPI
from app.api.routes import webhooks, admin

app = FastAPI(title="RazorPay Recovery Engine")

app.include_router(webhooks.router)
app.include_router(admin.router)
