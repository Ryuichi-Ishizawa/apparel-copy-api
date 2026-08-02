import os

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from apparel_copy_v4 import generate_copy, extract_known_facts

app = FastAPI(title="Apparel Copy API", version="1.0.0")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(api_key_header)):
    expected = os.environ.get("APP_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="サーバー側の APP_API_KEY が未設定です")
    if key != expected:
        raise HTTPException(status_code=401, detail="APIキーが正しくありません")
    return key


class CopyResult(BaseModel):
    visible_facts: str = ""
    product_name: str
    description: str
    category: str
    tags: list[str] = []
    uncertain: list[str] = []
    conflicts: list[str] = []


class FactsResult(BaseModel):
    known_facts_ja: str = ""
    not_found: list[str] = []


@app.post("/generate-copy", response_model=CopyResult, dependencies=[Depends(require_api_key)])
def generate_copy_endpoint(
    images: list[UploadFile] = File(..., description="商品画像（複数可）"),
    gender: str = Form("auto"),
    known_facts: str = Form(""),
    brand_notes: str = Form(""),
    revise: bool = Form(True),
):
    image_bytes = [img.file.read() for img in images]
    try:
        res = generate_copy(
            image_bytes,
            gender=gender,
            brand_notes=brand_notes,
            known_facts=known_facts,
            revise=revise,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"生成に失敗しました: {e}")
    return res


@app.post("/extract-facts", response_model=FactsResult, dependencies=[Depends(require_api_key)])
def extract_facts_endpoint(
    source_text: str = Form(..., description="仕入れ元ページのテキスト（英語など）"),
):
    try:
        return extract_known_facts(source_text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"抽出に失敗しました: {e}")


@app.get("/")
def health():
    return {"status": "ok"}
