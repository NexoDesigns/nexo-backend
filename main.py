from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from routers import documents, projects, rag, runs, webhooks

app = FastAPI(
    title="Nexo Designs API",
    version="0.3.0",
    description="Backend API for the Nexo Designs AI-assisted electronics design platform.",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production, restrict origins to the Vercel frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(projects.router)
app.include_router(runs.router)
app.include_router(webhooks.router)
app.include_router(documents.router)
app.include_router(rag.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": app.version}