import os
import time
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, FileResponse
from typing import List, Dict, Optional

# 导入内部模块
from backend.models import (
    BookCreateRequest,
    ChapterApproveRequest,
    ChapterGenerateRequest,
    NovelSaveRequest,
    APIKeySettings
)
from backend.database import BookRepository
from backend.ai_service import AIService

# 初始化 FastAPI 应用
app = FastAPI(title="AI Novel Creation Copilot API", version="1.0")

# 配置跨域中间件 (支持前端直接双击 index.html 跨域访问后端 API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = BookRepository()

# --- API 路由 ---

@app.get("/api/books")
def list_books():
    """获取所有书籍简要元数据"""
    return db.list_books()

@app.get("/api/books/{book_id}")
def get_book(book_id: str):
    """获取单部小说的完整 BookContext"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍项目未找到")
    return book

@app.post("/api/books")
def create_book(req: BookCreateRequest):
    """Workflow A: 创建新书，智能生成大纲与排期"""
    import math
    book_id = f"book-{int(time.time())}"
    
    # 辅助函数: 数字转中文
    def to_chinese_num(num: int) -> str:
        chinese_digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
        if num <= 9:
            return chinese_digits[num]
        elif num <= 19:
            return "十" + (chinese_digits[num % 10] if num % 10 != 0 else "")
        elif num <= 99:
            tens = num // 10
            ones = num % 10
            return chinese_digits[tens] + "十" + (chinese_digits[ones] if ones != 0 else "")
        return str(num)
        
    VOLUME_PRESETS = [
        "风起于青萍之末",
        "锋芒展露名四海",
        "风云变幻震八荒",
        "纵横捭阖问至尊",
        "超凡入圣踏天门",
        "大道归一乾坤定",
        "星河破裂苍穹碎",
        "纪元重塑造化生",
        "九极归一证因果",
        "天启重启万界归"
    ]
    
    # 每章平均3000字，计算总章数
    total_chapters = max(1, req.target_word_count // 3000)
    
    # 动态设定每卷章数，避免卷数过多或过少
    if total_chapters <= 10:
        chapters_per_volume = 5
    elif total_chapters <= 30:
        chapters_per_volume = 10
    else:
        chapters_per_volume = 15
        
    num_volumes = int(math.ceil(total_chapters / chapters_per_volume))
    
    volumes = []
    global_chapter_idx = 1
    
    for v_idx in range(num_volumes):
        v_num = v_idx + 1
        vol_preset_title = VOLUME_PRESETS[v_idx % len(VOLUME_PRESETS)]
        vol_title = f"第{to_chinese_num(v_num)}卷：{vol_preset_title}"
        
        # 本卷的章节列表
        vol_chapters = []
        vol_start_chapter = global_chapter_idx
        
        # 计算当前卷包含的章数 (最后一卷包含余数)
        current_vol_chapters_count = chapters_per_volume
        if v_idx == num_volumes - 1:
            current_vol_chapters_count = total_chapters - (v_idx * chapters_per_volume)
            
        for c_idx in range(current_vol_chapters_count):
            c_num = global_chapter_idx
            ch_title = f"第{to_chinese_num(c_num)}章：剧情推进与突破篇"
            ch_summary = f"在《{req.title}》的主线剧情推进下，主角林默（或对应主角）将在此章面临新的阶段性修行或外界危机。他需要逐步摸索力量规律，积蓄实力准备面对更大的挑战。"
            
            # 第一章和第二章进行特定趣味命名
            if c_num == 1:
                ch_title = "第一章：突如其来的变故"
                ch_summary = "交代故事发生的力量设定与初始危机，主角意外唤醒金手指，命运齿轮由此转动。"
            elif c_num == 2:
                ch_title = "第二章：破釜沉舟的修行"
                ch_summary = "主角开始熟悉金手指的使用规则，顶住各方压力并进行极限修炼，最终打破瓶颈崭露头角。"
                
            vol_chapters.append({
                "chapter_id": 100 * v_num + c_idx + 1,  # 卷号区分：第一卷101开始，第二卷201开始
                "title": ch_title,
                "summary": ch_summary,
                "status": "pending",
                "content": ""
            })
            global_chapter_idx += 1
            
        vol_end_chapter = global_chapter_idx - 1
        
        volumes.append({
            "volume_id": v_num,
            "volume_title": vol_title,
            "volume_summary": f"本卷包含第 {vol_start_chapter} 章至第 {vol_end_chapter} 章。讲述主角在《{req.title}》的世界背景中开启第一阶段的剧情推进，历经种种磨难与比斗，并在卷末实现阶段性小逆袭。",
            "chapters": vol_chapters
        })


    new_book = {
        "book_id": book_id,
        "meta": {
            "title": req.title,
            "tags": req.tags if req.tags else ["未分类"],
            "background": req.background,
            "synopsis": req.synopsis,
            "target_word_count": req.target_word_count,
            "daily_update_words": req.daily_update_words
        },
        "outline": {
            "volumes": volumes
        },
        "settings": {
            "current_model": "gemini-1.5-pro",
            "de_ai_level": "medium"
        }
    }

    db.save_book(new_book)
    return new_book

@app.delete("/api/books/{book_id}")
def delete_book(book_id: str):
    """删除某部小说"""
    success = db.delete_book(book_id)
    if not success:
        raise HTTPException(status_code=404, detail="书籍未找到")
    return {"status": "success", "message": "书籍删除成功"}

@app.put("/api/books/{book_id}/chapters/{chapter_id}/approve")
def approve_chapter_outline(book_id: str, chapter_id: int, req: ChapterApproveRequest):
    """Workflow B: 仅确认梗概，将状态更改为 approved (不生成正文)"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到书籍")
    
    found = False
    for vol in book["outline"]["volumes"]:
        for ch in vol["chapters"]:
            if ch["chapter_id"] == chapter_id:
                ch["title"] = req.title
                ch["summary"] = req.summary
                ch["status"] = "approved"
                found = True
                break
    
    if not found:
        raise HTTPException(status_code=404, detail="未找到章节")
        
    db.save_book(book)
    return book

@app.put("/api/books/{book_id}/chapters/{chapter_id}/revert")
def revert_chapter_status(book_id: str, chapter_id: int):
    """将章节状态回退到 pending (允许重新编辑梗概)"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到书籍")
    
    found = False
    for vol in book["outline"]["volumes"]:
        for ch in vol["chapters"]:
            if ch["chapter_id"] == chapter_id:
                ch["status"] = "pending"
                found = True
                break
    
    if not found:
        raise HTTPException(status_code=404, detail="未找到章节")
        
    db.save_book(book)
    return book

@app.put("/api/books/{book_id}/chapters/{chapter_id}/save")
def save_chapter_body(book_id: str, chapter_id: int, req: NovelSaveRequest):
    """手动保存小说正文，强制更新状态为 completed"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到书籍")
    
    found = False
    for vol in book["outline"]["volumes"]:
        for ch in vol["chapters"]:
            if ch["chapter_id"] == chapter_id:
                ch["content"] = req.content
                ch["status"] = "completed"
                found = True
                break
    
    if not found:
        raise HTTPException(status_code=404, detail="未找到章节")
        
    db.save_book(book)
    return book

@app.post("/api/books/{book_id}/chapters/{chapter_id}/generate")
def generate_chapter_body(book_id: str, chapter_id: int, req: ChapterGenerateRequest):
    """Workflow B: 推进章节，智能调用底座模型生成正文，进入De-AI管线"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到书籍")
    
    # 查找卷概要和对应章节大纲
    vol_summary = ""
    target_chapter = None
    
    for vol in book["outline"]["volumes"]:
        for ch in vol["chapters"]:
            if ch["chapter_id"] == chapter_id:
                vol_summary = vol["volume_summary"]
                target_chapter = ch
                break
                
    if not target_chapter:
        raise HTTPException(status_code=404, detail="章节未找到")

    # 更新前端传入的大纲标题和梗概内容
    target_chapter["title"] = req.title
    target_chapter["summary"] = req.summary

    # --- 两轮 Agent 生成管线 ---
    # 第一轮: Drafting (粗写初稿)
    model = book["settings"]["current_model"]
    draft_content = AIService.generate_draft(
        model=model,
        api_key=req.api_key,
        book_meta=book["meta"],
        volume_summary=vol_summary,
        chapter_title=req.title,
        chapter_summary=req.summary
    )

    # 第二轮: De-AI Polish (消除痕迹与拟人类润色)
    polished_content, changes = AIService.apply_de_ai_polish(draft_content)
    
    # 保存结果
    target_chapter["content"] = polished_content
    target_chapter["status"] = "completed"
    
    db.save_book(book)
    
    # 返回正文、去AI优化替换统计、以及设定逻辑校验
    logic_reports = AIService.check_logic_consistency(polished_content, book["meta"]["background"], book["meta"]["synopsis"])
    
    return {
        "status": "success",
        "chapter": target_chapter,
        "de_ai_changes": changes,
        "logic_reports": logic_reports
    }

@app.post("/api/books/{book_id}/chapters/{chapter_id}/de_ai")
def trigger_de_ai_polish(book_id: str, chapter_id: int):
    """对已存在的正文执行手动的 De-AI 痕迹清洗与优化，并保存"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到书籍")
        
    target_chapter = None
    for vol in book["outline"]["volumes"]:
        for ch in vol["chapters"]:
            if ch["chapter_id"] == chapter_id:
                target_chapter = ch
                break
                
    if not target_chapter or not target_chapter["content"]:
        raise HTTPException(status_code=400, detail="正文不存在，无法执行去AI优化")
        
    polished, changes = AIService.apply_de_ai_polish(target_chapter["content"])
    target_chapter["content"] = polished
    db.save_book(book)
    
    return {
        "status": "success",
        "content": polished,
        "changes": changes
    }

@app.post("/api/estimate")
def estimate_cost(
    model: str = Query(..., description="选择的模型"),
    input_text: str = Body("", embed=True, description="拼装完毕的上下文文本")
):
    """Workflow C: 预估 Token 与单次生成费用"""
    input_tokens = AIService.estimate_tokens(input_text)
    output_tokens = 3500  # 小说单章输出 Tokens 平均值
    cost = AIService.calculate_cost(model, input_tokens, output_tokens)
    
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost
    }

@app.get("/api/books/{book_id}/export", response_class=PlainTextResponse)
def export_book_markdown(book_id: str):
    """Workflow C: 将全书大纲与所有已生成正文打包导出为标准化 Markdown"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍未找到")
        
    md = f"# 《{book['meta']['title']}》\n\n"
    md += f"*   **标签/类型**: {', '.join(book['meta']['tags'])}\n"
    md += f"*   **核心简介**: {book['meta']['synopsis']}\n"
    md += f"*   **设定背景**: {book['meta']['background']}\n\n"
    md += "## 宏观大纲剧情推进\n\n"
    
    for vol in book["outline"]["volumes"]:
        md += f"### {vol['volume_title']}\n\n> {vol['volume_summary']}\n\n"
        for ch in vol["chapters"]:
            md += f"#### {ch['title']} [状态: {ch['status'].upper()}]\n\n"
            md += f"*剧情梗概: {ch['summary']}*\n\n"
            if ch["content"]:
                md += f"{ch['content']}\n\n"
            else:
                md += "*(正文待生成)*\n\n"
            md += "---\n\n"
            
    return md

@app.post("/api/models/discover")
def discover_models(req: APIKeySettings):
    """
    根据用户输入的 API Key，动态获取其当前有权限调用的实际可用模型列表。
    若获取失败 (如内网离线)，则根据填入的密钥返回高品质常用模型列表作为 fallback 备选。
    """
    import requests
    available_models = []
    
    # 1. 检测 Gemini 可用模型
    if req.gemini:
        gemini_added = False
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={req.gemini}"
            res = requests.get(url, timeout=10)
            if res.ok:
                data = res.json()
                for m in data.get("models", []):
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        name = m["name"].replace("models/", "")
                        disp = m.get("displayName", name)
                        available_models.append({
                            "provider": "gemini",
                            "model_id": name,
                            "display_name": f"Gemini - {disp}"
                        })
                        gemini_added = True
        except Exception as e:
            print(f"获取 Gemini 官方模型列表接口失败: {e}")
            
        if not gemini_added:
            available_models.extend([
                {"provider": "gemini", "model_id": "gemini-1.5-pro", "display_name": "Gemini - 1.5 Pro (推荐)"},
                {"provider": "gemini", "model_id": "gemini-1.5-flash", "display_name": "Gemini - 1.5 Flash (快速)"},
                {"provider": "gemini", "model_id": "gemini-2.0-flash-exp", "display_name": "Gemini - 2.0 Flash (试验)"}
            ])

    # 2. 检测 DeepSeek 可用模型
    if req.deepseek:
        deepseek_added = False
        try:
            url = "https://api.deepseek.com/v1/models"
            headers = {"Authorization": f"Bearer {req.deepseek}"}
            res = requests.get(url, headers=headers, timeout=10)
            if res.ok:
                data = res.json()
                for m in data.get("data", []):
                    name = m["id"]
                    available_models.append({
                        "provider": "deepseek",
                        "model_id": name,
                        "display_name": f"DeepSeek - {name}"
                    })
                    deepseek_added = True
        except Exception as e:
            print(f"获取 DeepSeek 官方模型列表接口失败: {e}")
            
        if not deepseek_added:
            available_models.extend([
                {"provider": "deepseek", "model_id": "deepseek-coder", "display_name": "DeepSeek - Coder (创作优化版)"},
                {"provider": "deepseek", "model_id": "deepseek-chat", "display_name": "DeepSeek - Chat (V3)"}
            ])

    return available_models

# --- 静态文件托管与主页面 ---
# 托管前端静态目录 frontend (放置 index.html 和静态资源)
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    @app.get("/")
    def read_root():
        return {"status": "ok", "message": "FastAPI 服务正常运行。未找到 frontend 静态目录，请创建此目录放置网页前端。"}
