import os
import time
import json
import math
import re
import datetime
import traceback
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, FileResponse, StreamingResponse
from typing import List, Dict, Optional

# 导入内部模块
from backend.models import (
    BookCreateRequest,
    ChapterApproveRequest,
    ChapterGenerateRequest,
    NovelSaveRequest,
    APIKeySettings, RegenerateOutlineRequest, SettingsUpdateRequest
)
from backend.database import BookRepository
from backend.ai_service import AIService

# 全局辅助函数: 数字转中文
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

# 初始化 FastAPI 应用
app = FastAPI(title="AI Novel Creation Copilot API", version="1.0")

# 配置跨域中间件 (支持前端直接双击 index.html 跨域访问后端 API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
    import uuid
    book_id = f"book-{uuid.uuid4().hex[:12]}"
    
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
                "chapter_id": 10000 * v_num + c_idx + 1,  # 卷号区分：第一卷10001开始，第二卷20001开始，每卷最大支持9999章，避免溢出碰撞
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
    polished_content, changes = AIService.apply_de_ai_polish(
        draft_content,
        model=model,
        api_key=req.api_key
    )
    
    # 保存结果
    target_chapter["content"] = polished_content
    target_chapter["status"] = "completed"
    
    db.save_book(book)
    
    # 返回正文、去AI优化替换统计、以及设定逻辑校验
    logic_reports = AIService.check_logic_consistency(
        polished_content,
        book["meta"]["background"],
        book["meta"]["synopsis"],
        model=model,
        api_key=req.api_key
    )
    
    return {
        "status": "success",
        "chapter": target_chapter,
        "de_ai_changes": changes,
        "logic_reports": logic_reports
    }

from backend.models import DeAiPolishRequest

@app.post("/api/books/{book_id}/chapters/{chapter_id}/de_ai")
def trigger_de_ai_polish(book_id: str, chapter_id: int, req: DeAiPolishRequest):
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
        
    model = book["settings"]["current_model"]
    polished, changes = AIService.apply_de_ai_polish(
        target_chapter["content"],
        model=model,
        api_key=req.api_key
    )
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
                        
                        name_lower = name.lower()
                        disp_lower = disp.lower()
                        # 过滤非纯文本生成模型，比如语音合成(TTS)、图像/视频生成、嵌入向量、双向翻译等
                        exclude_keywords = ["tts", "image", "audio", "embed", "vision", "bidi", "voice", "translation", "multimodal-preview"]
                        if any(kw in name_lower or kw in disp_lower for kw in exclude_keywords):
                            continue
                            
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

@app.post("/api/books/{book_id}/regenerate_outline")
def regenerate_book_outline(book_id: str, req: RegenerateOutlineRequest):
    """Workflow A-2: 根据书籍最新的设定背景与简介，重新生成整书卷章大纲 (流式进度返回)"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到书籍")

    if req.model and req.model.strip():
        book["settings"]["current_model"] = req.model.strip()
        db.save_book(book)

    def event_generator():
        if not req.api_key or not req.api_key.strip():
            yield f"data: {json.dumps({'event': 'error', 'message': '⚠️ 智能大纲规划失败: 未配置或激活大模型 API 密钥！请先在配置中心填写对应模型的 Key。'}, ensure_ascii=False)}\n\n"
            return

        words_per_chapter = book["meta"].get("words_per_chapter", 3000)
        target_word_count = book["meta"].get("target_word_count", 100000)
        total_chapters = max(1, target_word_count // words_per_chapter)
        
        if total_chapters <= 15:
            num_volumes = 1
            chapters_per_volume = total_chapters
        elif total_chapters <= 50:
            num_volumes = 2
            chapters_per_volume = int(math.ceil(total_chapters / 2))
        elif total_chapters <= 120:
            num_volumes = 3
            chapters_per_volume = int(math.ceil(total_chapters / 3))
        elif total_chapters <= 250:
            num_volumes = 4
            chapters_per_volume = int(math.ceil(total_chapters / 4))
        elif total_chapters <= 500:
            num_volumes = 6
            chapters_per_volume = int(math.ceil(total_chapters / 6))
        elif total_chapters <= 1000:
            num_volumes = 8
            chapters_per_volume = int(math.ceil(total_chapters / 8))
        else:
            num_volumes = 12
            chapters_per_volume = int(math.ceil(total_chapters / 12))
        
        is_resume = req.resume and book.get("outline", {}).get("volumes")
        existing_volumes = book.get("outline", {}).get("volumes", []) if is_resume else []
        
        successful_volumes = []
        for vol in existing_volumes:
            chaps = vol.get("chapters", [])
            if chaps and not any("(兜底篇)" in c.get("title", "") for c in chaps):
                successful_volumes.append(vol)
            else:
                break
                
        num_successful = len(successful_volumes)
        story_outline = book["meta"].get("synopsis", "")
        if is_resume and num_successful > 0:
            yield f"data: {json.dumps({'event': 'progress', 'percent': 5, 'message': f'🔌 启用断点续传！保留前 {num_successful} 卷已生成的章节大纲，继续往后规划...'}, ensure_ascii=False)}\n\n"
            volumes_result = successful_volumes.copy()
            if volumes_result:
                last_vol_chaps = volumes_result[-1].get("chapters", [])
                if len(last_vol_chaps) >= 2:
                    prev_chapters_info = f"- {last_vol_chaps[-2]['title']}: {last_vol_chaps[-2]['summary']}\n- {last_vol_chaps[-1]['title']}: {last_vol_chaps[-1]['summary']}"
                elif len(last_vol_chaps) == 1:
                    prev_chapters_info = f"- {last_vol_chaps[-1]['title']}: {last_vol_chaps[-1]['summary']}"
                else:
                    prev_chapters_info = ""
        else:
            volumes_result = []
            prev_chapters_info = ""

        volumes_outline = []
        if is_resume and len(existing_volumes) >= num_volumes:
            for vol in existing_volumes:
                volumes_outline.append({
                    "volume_num": vol.get("volume_id"),
                    "title": vol.get("volume_title"),
                    "summary": vol.get("volume_summary")
                })
            yield f"data: {json.dumps({'event': 'progress', 'percent': 15, 'message': '📋 复用已有的分卷划分，跳过大模型重新分卷...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'progress', 'percent': 10, 'message': '正在分析设定并梳理全书故事线起承转合...'}, ensure_ascii=False)}\n\n"
            planning_model = book["settings"]["current_model"] or "gemini-1.5-pro"
            
            story_prompt = f"""你是一个顶级小说大纲策划师。请为小说《{book['meta']['title']}》规划一份完整的故事线起承转合大纲。
小说背景设定：{book['meta']['background']}
小说核心简介与爽点：{book['meta']['synopsis']}
预计总章节数：{total_chapters}章，共分为{num_volumes}卷。

请详细写出该书的完整故事大纲，明确交代故事的开端、发展、冲突高潮和结局。
请直接返回故事大纲内容，不要包含任何引言、解释、前后客套话或 Markdown 格式的标题。"""
            
            try:
                story_outline = AIService._call_api(planning_model, req.api_key, story_prompt)
            except Exception as e:
                print(f"生成故事大纲失败: {e}")
    
            yield f"data: {json.dumps({'event': 'progress', 'percent': 25, 'message': '整体故事线规划完成！正在将故事划分并生成独特的卷大纲...'}, ensure_ascii=False)}\n\n"
            
            volume_prompt = f"""你是一个小说分卷大纲策划师。根据小说的完整故事大纲，将小说划分为 {num_volumes} 卷。
    
小说名称：《{book['meta']['title']}》
背景设定：{book['meta']['background']}
完整故事大纲：{story_outline}

请为这 {num_volumes} 卷中每一卷规划卷名（例如：第一卷：龙兴于野）以及该卷的核心剧情概要。每一卷的卷名必须独特且紧扣该卷剧情，严禁重复！
你必须返回符合以下JSON格式的纯JSON数据（JSON数组），不要包含 markdown 格式标记 (如 ```json) 或任何前后导言，确保它是一个有效的 JSON 数组：
[
  {{"volume_num": 1, "title": "第一卷：具体卷名", "summary": "本卷详细的故事起承转合与爽点发展..."}},
  ...
]
"""
            try:
                res_text = AIService._call_api(planning_model, req.api_key, volume_prompt)
                json_match = re.search(r"(\[.*\])", res_text, re.DOTALL)
                clean_text = json_match.group(1).strip() if json_match else re.sub(r"```json|```", "", res_text).strip()
                volumes_outline = json.loads(clean_text)
            except Exception as e:
                print(f"流式大纲分卷生成失败: {e}")
    
            VOLUME_PRESETS = ["风起于青萍之末", "锋芒展露名四海", "风云变幻震八荒", "纵横捭阖问至尊", "超凡入圣踏天门", "大道归一乾坤定", "星河破裂苍穹碎"]
                
            if not isinstance(volumes_outline, list) or len(volumes_outline) == 0:
                volumes_outline = []
            while len(volumes_outline) < num_volumes:
                v_num = len(volumes_outline) + 1
                vol_preset = VOLUME_PRESETS[(v_num - 1) % len(VOLUME_PRESETS)]
                volumes_outline.append({
                    "volume_num": v_num,
                    "title": f"第{to_chinese_num(v_num)}卷：{vol_preset}",
                    "summary": f"主角在这一阶段开启第 {v_num} 阶段的剧情推进，历经种种磨难，最终在本卷末尾实现阶段性小逆袭。"
                })

        for v_idx in range(num_volumes):
            v_num = v_idx + 1
            if is_resume and v_idx < num_successful:
                yield f"data: {json.dumps({'event': 'progress', 'percent': int(30 + (v_idx / num_volumes) * 65), 'message': f'✅ 第 {v_num}/{num_volumes} 卷已存在，跳过生成并保留数据...'}, ensure_ascii=False)}\n\n"
                continue

            v_title = volumes_outline[v_idx].get("title", f"第{v_num}卷")
            v_summary = volumes_outline[v_idx].get("summary", "")
            
            vol_start = (v_num - 1) * chapters_per_volume + 1
            vol_end = min(total_chapters, v_num * chapters_per_volume)
            
            percent = int(30 + (v_idx / num_volumes) * 65)
            yield f"data: {json.dumps({'event': 'progress', 'percent': percent, 'message': f'正在串行生成第 {v_num}/{num_volumes} 卷《{v_title}》的章节标题与细纲...'}, ensure_ascii=False)}\n\n"
            
            if not v_title.startswith(f"第{to_chinese_num(v_num)}卷"):
                v_title_clean = v_title.split("：")[-1].split(":")[-1].strip()
                v_title = f"第{to_chinese_num(v_num)}卷：{v_title_clean}"

            chapters = []
            BATCH_SIZE = 8
            current_start = vol_start
            batch_prev_info = prev_chapters_info
            
            try:
                while current_start <= vol_end:
                    current_end = min(vol_end, current_start + BATCH_SIZE - 1)
                    current_count = current_end - current_start + 1
                    
                    batch_context = ""
                    if batch_prev_info:
                        batch_context = f"前置的章节细纲梗概为：\n{batch_prev_info}\n请确保本次生成的第 {current_start} 章能够与前置章节顺畅衔接，不要产生剧情断层或逻辑冲突。"
                    
                    batch_prompt = f"""你是一个顶级小说章节细纲策划师。请为小说《{book['meta']['title']}》的第 {v_num} 卷《{v_title}》规划具体的章节细纲。
    
小说背景设定：{book['meta']['background']}
故事完整大纲：{story_outline}
本卷故事概要：{v_summary}
    
本次需要规划从第 {current_start} 章到第 {current_end} 章共 {current_count} 个章节。
你规划的章节名称必须遵循格式：'第X章：具体名字'。
前置剧情衔接：
{batch_context}

为了保持小说连贯性和逻辑一致，你必须返回符合以下JSON格式的纯JSON数据（JSON数组），不要包含 markdown 格式标记 (如 ```json) 或任何前后导言，确保它是一个有效的 JSON 数组：
[
  {{"title": "第{current_start}章：章节名", "summary": "本章包含的具体矛盾冲突，登场角色以及对核心简介主线的承接..."}},
  ...
]
"""
                    import time
                    if len(chapters) > 0: time.sleep(1.0)
                    planning_model = book["settings"]["current_model"] or "gemini-1.5-pro"
                    
                    res_text = AIService._call_api(planning_model, req.api_key, batch_prompt)
                    
                    json_match = re.search(r"(\[.*\])", res_text, re.DOTALL)
                    clean_text = json_match.group(1).strip() if json_match else re.sub(r"```json|```", "", res_text).strip()
                    batch_chapters = json.loads(clean_text)
                    
                    for idx, ch_data in enumerate(batch_chapters):
                        ch_num = current_start + idx
                        t = ch_data.get("title", f"第{to_chinese_num(ch_num)}章：剧情突破").strip()
                        s = ch_data.get("summary", "主角开始迎接新的挑战。").strip()
                        
                        if not t.startswith(f"第{to_chinese_num(ch_num)}章") and not t.startswith(f"第{ch_num}章"):
                            title_content = t.split("：")[-1].split(":")[-1].strip()
                            t = f"第{to_chinese_num(ch_num)}章：{title_content}"
                            
                        chapters.append({
                            "chapter_id": 10000 * v_num + (ch_num - vol_start) + 1,
                            "title": t,
                            "summary": s,
                            "status": "pending",
                            "content": ""
                        })
                        
                    if batch_chapters:
                        last_c = batch_chapters[-1]
                        batch_prev_info = f"- {last_c.get('title')}: {last_c.get('summary')}"
                        if len(batch_chapters) >= 2:
                            prev_c = batch_chapters[-2]
                            batch_prev_info = f"- {prev_c.get('title')}: {prev_c.get('summary')}\n" + batch_prev_info
                            
                    current_start = current_end + 1
                    
                prev_chapters_info = batch_prev_info
                
            except Exception as e:
                err_trace = traceback.format_exc()
                err_msg = f"流式生成第 {v_num} 卷章节失败: {e}"
                print(err_msg)
                
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                project_dir = os.path.dirname(backend_dir)
                debug_log_path = os.path.join(project_dir, "api_debug.log")
                try:
                    with open(debug_log_path, "a", encoding="utf-8") as lf:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        lf.write(f"[{timestamp}] [CRITICAL_ERROR] {err_msg}. 详细异常堆栈:\n{err_trace}\n")
                except Exception as log_err:
                    print(f"写入第 {v_num} 卷章节失败日志出错: {log_err}")
                
                yield f"data: {json.dumps({'event': 'error', 'message': f'第 {v_num} 卷生成失败: {str(e)}'}, ensure_ascii=False)}\n\n"
                return

            if not chapters:
                vol_chapters_count = vol_end - vol_start + 1
                phases = ["势起风骤", "顺水推舟", "异变陡生", "尘埃落定"]
                for c_idx in range(vol_chapters_count):
                    c_num = vol_start + c_idx
                    phase_name = phases[int((c_idx / vol_chapters_count) * len(phases)) % len(phases)]
                    clean_v_title = v_title.split("：")[-1].split(":")[-1].strip()
                    chapters.append({
                        "chapter_id": 100 * v_num + c_idx + 1,
                        "title": f"第{to_chinese_num(c_num)}章：{clean_v_title}之{phase_name} (兜底篇)",
                        "summary": f"在{v_title}的故事脉络下，剧情逐步推向“{phase_name}”节点。主角在此章面临新挑战，开始着手解决有关“{v_summary[:60]}”的具体剧情冲突。",
                        "status": "pending",
                        "content": ""
                    })

            # 校验章节名和章节梗概去重强检测
            seen_titles = set()
            seen_summaries = set()
            for ch in chapters:
                t = ch["title"].strip()
                s = ch["summary"].strip()
                if t in seen_titles:
                    raise ValueError(f"第 {v_num} 卷中检测到重复的章节标题: '{t}'")
                if s in seen_summaries:
                    raise ValueError(f"第 {v_num} 卷中检测到重复的章节梗概: '{s[:40]}...'")
                seen_titles.add(t)
                seen_summaries.add(s)

            volumes_result.append({
                "volume_id": v_num,
                "volume_title": v_title,
                "volume_summary": v_summary,
                "chapters": chapters
            })
            
            # 增量存盘：每生成好一卷就写入数据库并保存，确保中途断掉时数据能保留
            book["outline"]["volumes"] = volumes_result.copy()
            db.save_book(book)

        book["outline"]["volumes"] = volumes_result
        db.save_book(book)
        
        yield f"data: {json.dumps({'event': 'progress', 'percent': 100, 'message': '大纲规划重塑成功！正在渲染大纲结构...'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'event': 'complete', 'data': book}, ensure_ascii=False)}\n\n"
        
    def event_generator_wrapper():
        gen = event_generator()
        while True:
            try:
                event = next(gen)
                yield event
            except StopIteration:
                break
            except Exception as e:
                err_trace = traceback.format_exc()
                print(f"流式大纲生成发生未捕获异常:\n{err_trace}")
                
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                project_dir = os.path.dirname(backend_dir)
                debug_log_path = os.path.join(project_dir, "api_debug.log")
                try:
                    with open(debug_log_path, "a", encoding="utf-8") as f:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"[{timestamp}] [CRITICAL_ERROR] 大纲流式生成致命异常:\n{err_trace}\n")
                except Exception as log_err:
                    print(f"写入致命日志失败: {log_err}")
                
                yield f"data: {json.dumps({'event': 'error', 'message': f'❌ 大纲生成过程中发生错误: {str(e)}。详细请求返回和错误堆栈已记录在后端的 api_debug.log 中，请前往查看。'}, ensure_ascii=False)}\n\n"
                break
                
    return StreamingResponse(event_generator_wrapper(), media_type="text/event-stream")

@app.put("/api/books/{book_id}/settings")
def update_book_settings(book_id: str, req: SettingsUpdateRequest):
    """保存或更新小说大模型和去AI级别配置"""
    book = db.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到书籍")
    book["settings"]["current_model"] = req.current_model
    book["settings"]["de_ai_level"] = req.de_ai_level
    db.save_book(book)
    return {"status": "success", "settings": book["settings"]}

# 挂载前端静态文件托管 (必须放在最后，以防贪婪匹配路由被遮蔽)
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
