from fastapi import APIRouter, UploadFile, File
import shutil
import uuid
import os

from services.ai_pest_service import ai_service

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/detect")
async def detect_pest(file: UploadFile = File(...)):

    os.makedirs("uploads", exist_ok=True)

    file_path = f"uploads/{uuid.uuid4()}.jpg"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = ai_service.detect_pest(file_path)

    return {
        "result": result
    }