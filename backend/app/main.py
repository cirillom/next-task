import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.i18n import LocalizedText, localized, parameters
from app.routes import (
    auth,
    drafts,
    gemini,
    invitations,
    password_recovery,
    pomodoro,
    settings,
    tags,
    tasks,
)

app = FastAPI(title="Next Task", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(HTTPException)
async def localized_http_error(_request: Request, error: HTTPException) -> JSONResponse:
    detail = error.detail
    return JSONResponse(
        status_code=error.status_code,
        headers=error.headers,
        content={
            "detail": str(detail),
            "code": detail.key if isinstance(detail, LocalizedText) else "api.httpError",
            "params": parameters(detail.values)
            if isinstance(detail, LocalizedText)
            else {"status": error.status_code},
        },
    )


@app.exception_handler(RequestValidationError)
async def localized_validation_error(request: Request, error: RequestValidationError):
    response = await request_validation_exception_handler(request, error)
    body = json.loads(response.body)
    for original, rendered in zip(error.errors(), body["detail"], strict=True):
        cause = original.get("ctx", {}).get("error")
        text = cause.args[0] if isinstance(cause, Exception) and cause.args else None
        code, values = "validation.invalidValue", {}
        if isinstance(text, LocalizedText):
            code, values = text.key, parameters(text.values)
        elif original["type"] == "missing":
            code = "validation.required"
        elif original["type"] in ("string_too_short", "string_too_long"):
            minimum = original["type"] == "string_too_short"
            code = "validation.minLength" if minimum else "validation.maxLength"
            values = {"count": original["ctx"]["min_length" if minimum else "max_length"]}
        elif original["type"] in ("literal_error", "enum"):
            code = "validation.invalidChoice"
        rendered.update(code=code, params=values)
        rendered.pop("input", None)
        rendered.pop("ctx", None)
    return JSONResponse(status_code=422, content=body)


app.include_router(auth.router)
app.include_router(invitations.router)
app.include_router(password_recovery.router)
app.include_router(gemini.router)
app.include_router(pomodoro.router)
app.include_router(settings.router)
app.include_router(tags.router)
app.include_router(tasks.router)
app.include_router(drafts.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/{requested_path:path}", include_in_schema=False)
def frontend(requested_path: str) -> FileResponse:
    if requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail=localized("api.notFound"))
    frontend_dir = get_settings().frontend_dir.resolve()
    requested_file = (frontend_dir / requested_path).resolve()
    if requested_file.is_relative_to(frontend_dir) and requested_file.is_file():
        return FileResponse(requested_file)
    index = frontend_dir / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail=localized("api.frontendHasNotBeenBuilt"))
