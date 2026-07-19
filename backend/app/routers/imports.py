from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Account, ImportBatch
from app.repositories.imports import get_import_batch, save_import_batch
from app.schemas_imports import ApproveImportRequest, ApproveImportResponse, ImportBatchResponse
from app.services.screenshot_imports import approve_screenshot_import, process_screenshot_batch
from app.services.transactions import TransactionValidationError

router = APIRouter()
MAX_SCREENSHOT_SIZE = 15 * 1024 * 1024
ALLOWED_SCREENSHOT_TYPES = {"image/png", "image/jpeg", "image/webp"}


@router.post(
    "/imports/screenshots",
    response_model=ImportBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_screenshot(
    background_tasks: BackgroundTasks,
    account_id: int = Form(..., ge=1),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportBatch:
    """Validate and queue an explicitly confirmed local screenshot upload."""
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=400, detail="Account not found")
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_SCREENSHOT_TYPES:
        raise HTTPException(status_code=415, detail="Use a PNG, JPEG, or WebP screenshot")
    content = await file.read(MAX_SCREENSHOT_SIZE + 1)
    if len(content) > MAX_SCREENSHOT_SIZE:
        raise HTTPException(status_code=413, detail="Screenshot must be 15 MB or smaller")
    if not _matches_image_signature(content, content_type):
        raise HTTPException(status_code=415, detail="File contents do not match the image type")
    original_name = Path(file.filename or "screenshot").name
    directory = Path(get_settings().upload_dir) / "imports"
    directory.mkdir(parents=True, exist_ok=True)
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[content_type]
    stored_path = directory / f"{uuid4().hex}{extension}"
    stored_path.write_bytes(content)
    batch = save_import_batch(
        db,
        ImportBatch(
            original_filename=original_name,
            stored_path=str(stored_path),
            content_type=content_type,
            account_id=account.id,
            currency_code=account.currency_code,
            status="queued",
            progress=0,
        ),
    )
    background_tasks.add_task(process_screenshot_batch, batch.id)
    return batch


@router.get("/imports/{batch_id}", response_model=ImportBatchResponse)
def read_import_batch(batch_id: int, db: Session = Depends(get_db)) -> ImportBatch:
    batch = get_import_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return batch


@router.get("/imports/{batch_id}/image")
def read_import_image(batch_id: int, db: Session = Depends(get_db)) -> FileResponse:
    batch = get_import_batch(db, batch_id)
    if batch is None or not Path(batch.stored_path).is_file():
        raise HTTPException(status_code=404, detail="Import image not found")
    return FileResponse(batch.stored_path, media_type=batch.content_type)


@router.post("/imports/{batch_id}/approve", response_model=ApproveImportResponse)
def approve_import(
    batch_id: int,
    payload: ApproveImportRequest,
    db: Session = Depends(get_db),
) -> ApproveImportResponse:
    try:
        return approve_screenshot_import(db, batch_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, TransactionValidationError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _matches_image_signature(content: bytes, content_type: str) -> bool:
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    return signatures.get(content_type, False)
