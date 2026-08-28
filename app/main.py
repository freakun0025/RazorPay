from fastapi import FastAPI

app = FastAPI(title="Revenue Recovery Engine")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
