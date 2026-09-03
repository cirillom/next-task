from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routes import auth, tags, tasks, workspaces

app = FastAPI(title="Next Task", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(tags.router)
app.include_router(tasks.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/{requested_path:path}", include_in_schema=False)
def frontend(requested_path: str) -> FileResponse:
    if requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    frontend_dir = get_settings().frontend_dir.resolve()
    requested_file = (frontend_dir / requested_path).resolve()
    if requested_file.is_relative_to(frontend_dir) and requested_file.is_file():
        return FileResponse(requested_file)
    index = frontend_dir / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend has not been built")
