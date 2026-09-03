from fastapi import FastAPI

from app.routes import auth, tags, tasks, workspaces

app = FastAPI(title="Next Task", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(tags.router)
app.include_router(tasks.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
