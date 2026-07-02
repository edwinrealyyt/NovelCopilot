from pydantic import BaseModel
from typing import List, Dict, Optional, Union

# --- Pydantic API Models ---

class BookMeta(BaseModel):
    title: str
    tags: List[str]
    background: str
    synopsis: str
    target_word_count: int
    daily_update_words: int

class Chapter(BaseModel):
    chapter_id: int
    title: str
    summary: str
    status: str  # pending, approved, completed
    content: Optional[str] = ""

class Volume(BaseModel):
    volume_id: int
    volume_title: str
    volume_summary: str
    chapters: List[Chapter]

class Outline(BaseModel):
    volumes: List[Volume]

class BookSettings(BaseModel):
    current_model: str
    de_ai_level: str  # low, medium, high

class BookContext(BaseModel):
    book_id: str
    meta: BookMeta
    outline: Outline
    settings: BookSettings

class BookCreateRequest(BaseModel):
    title: str
    tags: Optional[List[str]] = []
    background: str
    synopsis: str
    target_word_count: int = 500000
    daily_update_words: int = 6000

class ChapterApproveRequest(BaseModel):
    title: str
    summary: str

class ChapterGenerateRequest(BaseModel):
    title: str
    summary: str
    api_key: Optional[str] = ""

class NovelSaveRequest(BaseModel):
    content: str

class APIKeySettings(BaseModel):
    gemini: Optional[str] = ""
    deepseek: Optional[str] = ""
    claude: Optional[str] = ""
