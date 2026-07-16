from pathlib import Path

import config
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.schemas.jobs import SceneOption, TemplateOption, UploadMetadataResponse
from chains.export_chain import TEMPLATE_SOURCE_DIR, list_templates
from prompts.templates import PromptTemplateLoader
from services.meeting_service import ASR_MODEL_SENSEVOICE, ASR_MODEL_WHISPER

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/upload", response_model=UploadMetadataResponse)
def get_upload_metadata() -> UploadMetadataResponse:
    scenes = [
        SceneOption(
            scene=item["scene"],
            display_name=item["display_name"],
            description=item["description"],
        )
        for item in PromptTemplateLoader.list_scenes()
    ]
    templates = [
        TemplateOption(
            name=item["name"],
            label=item["label"],
            has_docx=item["has_docx"],
            has_pdf=item["has_pdf"],
            preview_path=f"/meta/templates/{item['name']}/preview"
            if item.get("preview_path")
            else None,
        )
        for item in list_templates()
    ]

    return UploadMetadataResponse(
        scenes=scenes,
        templates=templates,
        output_formats=["docx", "md", "pdf"],
        asr_models=[ASR_MODEL_WHISPER, ASR_MODEL_SENSEVOICE],
        chunk_strategies=[
            {"value": config.CHUNK_STRATEGY_FIXED, "label": "固定 512 字"},
            {"value": config.CHUNK_STRATEGY_SEGMENT, "label": "按句子合并 300 字"},
            {"value": config.CHUNK_STRATEGY_SEMANTIC, "label": "语义切分"},
        ],
        transcription_modes=[
            {"value": "auto", "label": "自动（按时长）"},
            {"value": "direct", "label": "直接转写"},
            {"value": "parallel", "label": "并行转写"},
        ],
    )


@router.post("/templates/upload")
async def upload_template(file: UploadFile = File(...)) -> dict:
    """上传自定义导出模板（.docx 或 .pdf）"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".docx", ".pdf"}:
        raise HTTPException(status_code=400, detail="仅支持 .docx 或 .pdf 模板文件")

    TEMPLATE_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "template").stem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in safe_name)
    dest = TEMPLATE_SOURCE_DIR / f"{safe_name}{suffix}"

    content = await file.read()
    dest.write_bytes(content)

    return {"name": safe_name, "suffix": suffix, "size": len(content)}


@router.get("/templates/{template_name}/preview")
def get_template_preview(template_name: str) -> FileResponse:
    template = next(
        (item for item in list_templates() if item["name"] == template_name),
        None,
    )
    if not template or not template.get("preview_path"):
        raise HTTPException(status_code=404, detail="模板预览不存在")

    preview_path = Path(template["preview_path"])
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="模板预览不存在")

    return FileResponse(preview_path, media_type="image/png")
