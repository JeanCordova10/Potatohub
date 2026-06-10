from fastapi import FastAPI

app = FastAPI(
    title="PotatoHub API",
    description="Plataforma NoSQL de Recetas de Papa — PUCP 2026-1",
    version="1.0.0"
)

@app.get("/health", tags=["sistema"])
async def health():
    return {"status": "ok", "servicio": "PotatoHub API"}