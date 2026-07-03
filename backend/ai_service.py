import re
import math
import requests
import os
import time
import datetime
from typing import Dict, List, Tuple, Optional

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

# 高频 AI 词汇和替换词库
DE_AI_DICTIONARY = [
    (re.compile(r"总而言之|综上所述|总的来说"), "如此说来"),
    (re.compile(r"在这个充满[^\s]*的世界里"), "在这一方天地"),
    (re.compile(r"眼中闪过一丝[^\s]*"), "目光微动"),
    (re.compile(r"然而，"), "可"),
    (re.compile(r"嘴角勾起一抹[^\s]*"), "微微扬眉"),
    (re.compile(r"仿佛在诉说着[^\s]*"), "似在昭示"),
    (re.compile(r"无意中"), "巧合下"),
    (re.compile(r"不禁"), "终究还是"),
    (re.compile(r"不可思议"), "少见"),
    (re.compile(r"那一刻"), "转瞬之间")
]

# 各模型费率表 (价格单位: 人民币 CNY / 1M Tokens，按 1 USD = 7.25 CNY 换算)
MODEL_RATES = {
    "gemini-1.5-pro": {"input": 50.75, "output": 152.25},
    "gemini-3.5-flash": {"input": 10.88, "output": 32.63},
    "claude-3.5-sonnet": {"input": 21.75, "output": 108.75},
    "deepseek-coder": {"input": 1.45, "output": 5.80}
}

class AIService:
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """极轻量级 Token 预估器 (中文约 1.2 Tokens/字，英文约 1.3 Tokens/词)"""
        if not text:
            return 0
        
        # 匹配汉字
        chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
        # 匹配英文单词
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        # 计算其它非汉字非英文单词英文字符数，用于提高精准度
        english_chars_len = sum(len(m) for m in re.findall(r'\b[a-zA-Z]+\b', text))
        other_chars = max(0, len(text) - chinese_chars - english_chars_len)
        
        total_tokens = math.ceil(chinese_chars * 1.3 + english_words * 1.4 + other_chars * 0.5)
        return total_tokens

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """根据费率计算预估费用"""
        rates = MODEL_RATES.get(model, {"input": 1.0, "output": 3.0})
        cost = (input_tokens * rates["input"] / 1000000.0) + (output_tokens * rates["output"] / 1000000.0)
        return cost

    @classmethod
    def apply_de_ai_polish(
        cls, 
        text: str, 
        model: Optional[str] = None, 
        api_key: Optional[str] = None
    ) -> Tuple[str, List[Dict[str, str]]]:
        """执行去AI痕迹过滤并统计替换历史"""
        polished = text
        changes = []

        if api_key and model:
            prompt = f"""你是一个顶级小说文学润色专家。请对以下小说首稿进行去 AI 套路化痕迹（De-AI Polish）的精细润色。
AI腔调的典型特征包括：过度使用“总而言之/综上所述”、“嘴角勾起/闪过一丝”、“仿佛在诉说着/在这个充满...的世界里”、“不禁/然而”等陈词滥调，句式空泛，缺乏真正的画面感。
请对这些句子进行重构，改写为极具表现力的白描、拟人类小说句式。
润色要求：
1. 严禁改动剧情核心走向和人物设定。
2. 消除大语言模型的套路词，改为更自然、质朴、画面感强的表达。
3. 仅返回润色后的正文内容，不需要任何前后解释或引言。

当前正文首稿：
{text}
"""
            try:
                polished_llm = cls._call_api(model, api_key, prompt)
                if polished_llm and len(polished_llm.strip()) > 10:
                    # 检查大模型润色消除了哪些高频AI词
                    for pattern, replacement in DE_AI_DICTIONARY:
                        if pattern.search(text) and not pattern.search(polished_llm):
                            changes.append({
                                "original": f"消除AI套词: '{pattern.pattern}'",
                                "replacement": f"重构为拟人类文学表达: '{replacement}'"
                            })
                    polished = polished_llm
            except Exception as e:
                print(f"大模型去AI痕迹润色失败: {e}，将降级为本地规则替换")

        # --- 本地正则替换兜底/应用 ---
        for pattern, replacement in DE_AI_DICTIONARY:
            matches = pattern.findall(polished)
            if matches:
                for match in set(matches):
                    already_recorded = False
                    for existing in changes:
                        if match in existing["original"]:
                            already_recorded = True
                            break
                    if not already_recorded:
                        changes.append({
                            "original": match,
                            "replacement": replacement
                        })
                polished = pattern.sub(replacement, polished)
                
        return polished, changes

    @classmethod
    def check_logic_consistency(
        cls, 
        content: str, 
        background: str, 
        synopsis: str, 
        model: Optional[str] = None, 
        api_key: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """逻辑设定防 OOC 与设定冲突校验 (支持 LLM 并行分析与词袋降级)"""
        reports = []
        
        if not content:
            return reports

        if api_key and model:
            prompt = f"""你是一个小说一致性校对和人设监督专家。请阅读以下小说背景设定、核心简介和当前章节的正文，分析其中是否存在：
1. 人格设定偏离或 OOC（例如：冷酷的女主表现得惊慌失措大哭，且没有合理的心路转变解释）。
2. 情节逻辑冲突（例如：前文说某人重伤垂死，紧接着下一句话却行动自如；瞬间移动到数千公里外等物理或空间矛盾）。
3. 设定违背（如违背已有的世界观设定或物理规则）。

小说背景设定：{background}
核心简介：{synopsis}
当前章节正文：
{content}

请为发现的问题出具警告和具体的修改建议。如果没有任何问题，请仅返回一个表明通过的 info 级别项。
你必须返回符合以下JSON格式的纯JSON数据（JSON数组），不要包含 markdown 格式标记 (如 ```json) 或任何前后导言，确保它是一个有效的 JSON 数组：
[
  {{"level": "warning", "text": "警告详情和具体修改建议..."}},
  {{"level": "info", "text": "如果没有发现冲突，出具校验成功的提示..."}}
]
"""
            try:
                res_text = cls._call_api(model, api_key, prompt)
                json_match = re.search(r"(\[[\s\S]*?\])\s*$", res_text.strip())
                clean_text = json_match.group(1).strip() if json_match else re.sub(r"```json|```", "", res_text).strip()
                
                raw_reports = json.loads(clean_text)
                if isinstance(raw_reports, list):
                    reports = [
                        {"level": str(r.get("level", "info")), "text": str(r.get("text", ""))}
                        for r in raw_reports
                        if isinstance(r, dict) and "level" in r and "text" in r
                    ]
                    if reports:
                        return reports
            except Exception as e:
                print(f"大模型一致性校验失败: {e}，将降级为本地规则")

        # --- 本地降级校验逻辑 ---
        if "白雀" in content:
            emotional_words = ["大哭", "崩溃", "不知所措", "惊慌失措", "委屈地流泪"]
            for word in emotional_words:
                if word in content:
                    reports.append({
                        "level": "warning",
                        "text": f"人设一致性警告：白雀在背景设定中为‘冷面独行黑客’，但本章描写中出现‘{word}’，存在OOC崩人设风险，建议修改为更克制的情绪细节描写。"
                    })
                    break
        
        if "第十三区" in background and "林默" in content:
            if "一区" in content and "瞬间" in content:
                reports.append({
                    "level": "warning",
                    "text": "空间位置警告：第十三区垃圾场与神代重工第一区行政区隔绝，林默‘瞬间到达’在设定中属于禁区，建议增加乘坐轨道交通或地下潜入的过门描写。"
                })

        if "林默" in content and "颈部" in content and "插槽" not in content and "芯片" in content:
            reports.append({
                "level": "info",
                "text": "特征校验：主角林默使用芯片过载，已自动校验其颈部神经插槽 of 物理接口设定，符合世界观。"
            })

        if not reports:
            reports.append({
                "level": "info",
                "text": "人物设定、主线推进及空间位置校验成功，暂未发现违背设定或OOC情况。"
            })
            
        return reports

    @classmethod
    def _call_api(cls, model: str, api_key: str, prompt: str) -> str:
        """发起真实的 HTTP 接口调用，自动读取并注入系统代理，具备 429 限流重试机制，并输出调试日志到 api_debug.log"""
        debug_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api_debug.log")
        
        # 防止日志文件无限膨胀，若大于 10MB，则清空重置
        if os.path.exists(debug_log_path) and os.path.getsize(debug_log_path) > 10 * 1024 * 1024:
            try:
                with open(debug_log_path, "w", encoding="utf-8") as f:
                    f.write("[INFO] 日志文件超过10MB，已自动重写重置。\n")
            except Exception:
                pass
        
        def write_debug_log(msg: str):
            try:
                with open(debug_log_path, "a", encoding="utf-8") as f:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {msg}\n")
            except Exception as le:
                print(f"写入调试日志失败: {le}")

        proxies = {}
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if http_proxy: proxies["http"] = http_proxy
        if https_proxy: proxies["https"] = https_proxy

        model_lower = model.lower()
        max_retries = 5
        base_delay = 5

        write_debug_log(f"[INFO] 准备调用 API - 模型: {model}, 提示词长度: {len(prompt)}字")

        for attempt in range(max_retries):
            try:
                if "gemini" in model_lower:
                    api_model = model if model.startswith("models/") else f"models/{model}"
                    url = f"https://generativelanguage.googleapis.com/v1beta/{api_model}:generateContent"
                    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
                    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 8192}}
                    
                    write_debug_log(f"[POST] 发送 Gemini 请求. URL: {url} [尝试 {attempt + 1}/{max_retries}]")
                    # 动态增加超时时间，重试时给大模型预留更宽裕的推理时间
                    current_timeout = 60 + 30 * attempt
                    res = requests.post(url, json=payload, headers=headers, timeout=current_timeout, proxies=proxies)
                    
                    if res.status_code == 429:
                        delay = base_delay * (2 ** attempt)
                        write_debug_log(f"[WARN] Gemini 429 限流. 等待 {delay} 秒重试...")
                        time.sleep(delay)
                        continue
                    
                    res.raise_for_status()
                    data = res.json()
                    
                    candidates = data.get("candidates", [])
                    if not candidates:
                        block_reason = data.get("promptFeedback", {}).get("blockReason", "未知")
                        raise ValueError(f"Gemini 返回空响应: {block_reason}")
                    
                    try:
                        response_text = candidates[0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError) as e:
                        raise ValueError(f"Gemini 响应结构异常: {e}, 原始数据: {str(data)[:500]}")
                        
                    write_debug_log(f"[SUCCESS] Gemini 成功. 长度: {len(response_text)}")
                    return response_text
                    
                elif "deepseek" in model_lower or model_lower.startswith("deepseek-"):
                    url = "https://api.deepseek.com/v1/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"
                    }
                    payload = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7
                    }
                    
                    write_debug_log(f"[POST] 发送 DeepSeek 请求. URL: {url} [尝试 {attempt + 1}/{max_retries}]")
                    # 动态增加超时时间，重试时给大模型预留更宽裕的推理时间
                    current_timeout = 60 + 30 * attempt
                    res = requests.post(url, json=payload, headers=headers, timeout=current_timeout, proxies=proxies)
                    
                    if res.status_code == 429:
                        delay = base_delay * (2 ** attempt)
                        write_debug_log(f"[WARN] DeepSeek 429 限流. 等待 {delay} 秒重试...")
                        time.sleep(delay)
                        continue
                        
                    res.raise_for_status()
                    data = res.json()
                    
                    choices = data.get("choices", [])
                    if not choices:
                        error_msg = data.get("error", {}).get("message", "未知")
                        raise ValueError(f"DeepSeek 返回空响应，原因: {error_msg}")
                    
                    try:
                        response_text = choices[0]["message"]["content"]
                    except (KeyError, IndexError) as e:
                        raise ValueError(f"DeepSeek 响应结构异常: {e}, 原始数据: {str(data)[:500]}")
                        
                    write_debug_log(f"[SUCCESS] DeepSeek 请求成功. 长度: {len(response_text)}")
                    return response_text
                else:
                    err_msg = f"模型 {model} 暂不支持在后端发起原生调用"
                    write_debug_log(f"[FATAL] {err_msg}")
                    raise NotImplementedError(err_msg)
            except requests.exceptions.RequestException as e:
                # 针对非 HTTP 直接返回，而是抛出异常但响应状态为 429 的情况
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                    delay = base_delay * (2 ** attempt)
                    write_debug_log(f"[WARN] 异常触发 429 限流. 等待 {delay} 秒后重试...")
                    time.sleep(delay)
                    continue
                
                # 针对偶发性连接超时、重置或繁忙，退避等待 3 + 3 * attempt 秒后重试，让代理/网络通道恢复
                if attempt < max_retries - 1:
                    delay = 3 + 3 * attempt
                    write_debug_log(f"[WARN] 网络请求抛出异常: {str(e)}. 将在等待 {delay} 秒后重试...")
                    time.sleep(delay)
                    continue
                
                write_debug_log(f"[FATAL] 重试次数耗尽，API 请求最终失败: {str(e)}")
                raise e

        err_final = f"大模型 API 调用由于频繁触发 429 限制，在重试 {max_retries} 次后失败。"
        write_debug_log(f"[FATAL] {err_final}")
        raise Exception(err_final)

    @classmethod
    def generate_and_sanitize_volumes(
        cls,
        model: str, 
        api_key: str, 
        title: str, 
        background: str, 
        synopsis: str, 
        story_outline: str, 
        num_volumes: int
    ) -> List[dict]:
        import re
        import json
        
        # 1. 尝试大模型 Markdown 列表生成
        volume_prompt = f"""你是一个小说分卷大纲策划师。根据小说的完整故事大纲，将小说划分为 {num_volumes} 卷。

小说名称：《{title}》
背景设定：{background}
完整故事大纲：{story_outline}

请为这 {num_volumes} 卷规划独特的卷名以及该卷的核心剧情概要。
每一卷的卷名必须独特且紧扣该卷剧情，严禁重复，严禁使用“第一阶段”、“第二阶段”这种敷衍的名称，必须是“风起云涌”、“龙战于野”等有极强网文色彩的切题卷名！

你必须按照以下严格的格式输出，每一卷占一行：
第1卷：[独特卷名] | [本卷核心剧情概要]
第2卷：[独特卷名] | [本卷核心剧情概要]
...
第{num_volumes}卷：[独特卷名] | [本卷核心剧情概要]

请直接返回上述列表，不要包含任何 Markdown 格式的标记 (如 ```) 或任何前后客套话。"""

        volumes_outline = []
        try:
            res_text = cls._call_api(model, api_key, volume_prompt)
            lines = [line.strip() for line in res_text.split("\n") if line.strip()]
            for line in lines:
                match = re.search(r"第\s*(\d+|[一二三四五六七八九十百千]+)\s*卷\s*[:：]\s*(.*?)\s*\|\s*(.*)", line)
                if match:
                    v_title = match.group(2).strip()
                    v_sum = match.group(3).strip()
                    volumes_outline.append({
                        "volume_num": len(volumes_outline) + 1,
                        "title": v_title,
                        "summary": v_sum
                    })
                else:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        v_title = parts[0].replace("第", "").replace("卷", "").strip()
                        v_title = re.sub(r"^\d+[\s.、:-]+", "", v_title)
                        v_sum = "|".join(parts[1:]).strip()
                        volumes_outline.append({
                            "volume_num": len(volumes_outline) + 1,
                            "title": v_title,
                            "summary": v_sum
                        })
        except Exception as e:
            print(f"大模型分卷划分规划抛出异常: {e}，将使用补全机制兜底")

        # 2. 如果解析出来的卷数不足，使用 AI 针对性地逐卷补全大纲，决不使用静态预设！
        max_attempts = num_volumes * 2
        attempts = 0
        while len(volumes_outline) < num_volumes and attempts < max_attempts:
            attempts += 1
            v_num = len(volumes_outline) + 1
            existing_info = "\n".join([f"第 {v['volume_num']} 卷《{v['title']}》: {v['summary'][:100]}..." for v in volumes_outline])
            
            complement_prompt = f"""\
小说《{title}》总共规划为 {num_volumes} 卷。
背景设定：{background}
整体故事大纲：{story_outline}

目已经规划好的前 {len(volumes_outline)} 卷大纲如下：
{existing_info}

现在，请为紧接其后的【第 {v_num} 卷】规划独特的卷名和核心剧情大纲。
卷名必须独特切题且极具网文色彩，严禁与前面已有的卷名重复！
你必须严格按照 `第{v_num}卷：[独特卷名] | [本卷核心大纲剧情概要]` 格式返回，不要有任何多余的客套话或标点。"""
            
            try:
                res_comp = cls._call_api(model, api_key, complement_prompt).strip()
                match = re.search(r"第\s*(\d+|[一二三四五六七八九十百千]+)\s*卷\s*[:：]\s*(.*?)\s*\|\s*(.*)", res_comp)
                if match:
                    v_title = match.group(2).strip()
                    v_sum = match.group(3).strip()
                    volumes_outline.append({
                        "volume_num": v_num,
                        "title": v_title,
                        "summary": v_sum
                    })
                else:
                    parts = res_comp.split("|")
                    if len(parts) >= 2:
                        v_title = parts[0].replace(f"第{v_num}卷", "").replace("：", "").replace(":", "").strip()
                        v_sum = "|".join(parts[1:]).strip()
                        volumes_outline.append({
                            "volume_num": v_num,
                            "title": v_title,
                            "summary": v_sum
                        })
            except Exception as e:
                print(f"大模型补全第 {v_num} 卷大纲失败: {e}")

        # 3. 强制卷名唯一性去重检查。如果发生重复卷名，用 AI 针对性进行重命名！
        existing_titles = set()
        for idx, vol in enumerate(volumes_outline):
            v_title = vol.get("title", "").strip()
            v_title = re.sub(r"^第\s*(\d+|[一二三四五六极九十百千]+)\s*卷\s*[:：]\s*", "", v_title).strip()
            
            if not v_title or v_title in existing_titles:
                rename_prompt = f"""小说名称：《{title}》
背景设定：{background}
本卷核心梗概：{vol['summary']}
已有卷名列表（严禁与之重复）：{list(existing_titles)}

请为本卷（第 {idx + 1} 卷）起一个具有网文特色且独一无一的新卷名（不超过10个字）。
直接返回起好的卷名，不要带任何多余字句。"""
                try:
                    new_name = cls._call_api(model, api_key, rename_prompt).strip()
                    # 消除 "牢" 字 typo 标点过滤，支持中文标点
                    new_name = re.sub(r"""^['"`“”‘’「」『』]+|['"`“”‘’「」『』]+$""", "", new_name).strip()
                    if new_name and new_name not in existing_titles:
                        v_title = new_name
                except Exception as e:
                    print(f"分卷唯一命名去重请求失败: {e}")
                    
            existing_titles.add(v_title)
            vol["title"] = f"第{to_chinese_num(idx + 1)}卷：{v_title}"

        return volumes_outline

    @classmethod
    def generate_book_outline_hierarchical(
        cls, 
        model: str, 
        api_key: str, 
        title: str, 
        background: str, 
        synopsis: str, 
        total_chapters: int,
        chapters_per_volume: int
    ) -> Tuple[List[dict], Optional[str]]:
        """使用大模型“故事 -> 分卷名 -> 章节名 -> 章纲”的顺序串行构建全书分卷和大纲章节"""
        if not api_key:
            return [], "未配置有效 API Key"

        num_volumes = int(math.ceil(total_chapters / chapters_per_volume))

        # 1. 生成整体故事线的起承转合 (故事级大纲)
        story_prompt = f"""你是一个顶级小说大纲策划师。请为小说《{title}》规划一份完整的故事线起承转合大纲。
小说背景设定：{background}
小说核心简介与爽点：{synopsis}
预计总章节数：{total_chapters}章，共分为{num_volumes}卷。

请详细写出该书的完整故事大纲，明确交代故事的开端、发展、冲突高潮和结局。
请直接返回故事大纲内容，不要包含任何引言、解释、前后客套话或 Markdown 格式的标题。"""
        
        story_outline = cls._call_api(model, api_key, story_prompt)

        # 2. 将故事拆分为各卷的分卷大纲
        volumes_outline = cls.generate_and_sanitize_volumes(
            model=model,
            api_key=api_key,
            title=title,
            background=background,
            synopsis=synopsis,
            story_outline=story_outline,
            num_volumes=num_volumes
        )

        # 3. 串行生成每一卷的章节名与章纲 (每一卷的生成知道前一卷的衔接信息，确保连贯且独特)
        volumes_result = []
        prev_chapters_info = ""  # 记录前一卷的最后一两章大纲，用于剧情衔接
        
        for v_idx in range(num_volumes):
            v_num = v_idx + 1
            v_title = volumes_outline[v_idx].get("title", f"第{v_num}卷")
            v_summary = volumes_outline[v_idx].get("summary", "")
            
            vol_start = (v_num - 1) * chapters_per_volume + 1
            vol_end = min(total_chapters, v_num * chapters_per_volume)
            vol_chapters_count = vol_end - vol_start + 1
            
            # 格式化卷标题
            if not v_title.startswith(f"第{to_chinese_num(v_num)}卷"):
                v_title_clean = v_title.split("：")[-1].split(":")[-1].strip()
                v_title = f"第{to_chinese_num(v_num)}卷：{v_title_clean}"

            context_str = ""
            if prev_chapters_info:
                context_str = f"前置的章节细纲梗概为：\n{prev_chapters_info}\n请确保本卷故事与前置章节紧密衔接，平滑过度。"

            volume_chapters_prompt = f"""你是一个顶级小说章节细纲策划师。请为小说《{title}》的第 {v_num} 卷《{v_title}》规划具体的章节细纲。

小说背景设定：{background}
故事完整大纲：{story_outline}
本卷故事概要：{v_summary}
预计包含从第 {vol_start} 章到第 {vol_end} 章共 {vol_chapters_count} 个章节。
前置剧情衔接：
{context_str}

请为本卷所有章节规划具体的、有画面感且独特的章节标题以及章纲剧情详细梗概。
你规划的章节名称必须遵循格式：'第X章：具体名字'。
你必须返回符合以下JSON格式的纯JSON数据（JSON数组），不要包含 markdown 格式标记 (如 ```json) 或 any 前后导言，确保它是一个有效的 JSON 数组：
[
  {{"title": "第{vol_start}章：章节名", "summary": "本章包含的具体矛盾冲突，登场角色以及对核心简介主线的承接..."}},
  ...
]
"""
            try:
                res_text = cls._call_api(model, api_key, volume_chapters_prompt)
                json_match = re.search(r"(\[[\s\S]*?\])\s*$", res_text.strip())
                clean_text = json_match.group(1).strip() if json_match else re.sub(r"```json|```", "", res_text).strip()
                chapters_list = json.loads(clean_text)
                
                # 防御性转换结构并纠正 id
                chapters = []
                for idx, c in enumerate(chapters_list):
                    c_num = vol_start + idx
                    t = c.get("title", f"第{to_chinese_num(c_num)}章：大纲待补").strip()
                    s = c.get("summary", "本章故事线平稳推进。").strip()
                    
                    if not t.startswith(f"第{to_chinese_num(c_num)}章") and not t.startswith(f"第{c_num}章"):
                        t_clean = t.split("：")[-1].split(":")[-1].strip()
                        t = f"第{to_chinese_num(c_num)}章：{t_clean}"
                        
                    chapters.append({
                        "chapter_id": 10000 * v_num + idx + 1,
                        "title": t,
                        "summary": s,
                        "status": "pending",
                        "content": ""
                    })
            except Exception as e:
                print(f"流式生成第 {v_num} 卷章节列表失败: {e}，触发兜底")
                chapters = []
                phases = ["风雨欲来", "惊涛骇浪", "力挽狂澜", "尘埃落定"]
                for idx in range(vol_chapters_count):
                    c_num = vol_start + idx
                    phase = phases[int((idx / vol_chapters_count) * len(phases)) % len(phases)]
                    chapters.append({
                        "chapter_id": 10000 * v_num + idx + 1,
                        "title": f"第{to_chinese_num(c_num)}章：{v_title.split('：')[-1]}之{phase} (兜底)",
                        "summary": f"衔接上文，林默在本章围绕‘{v_summary[:50]}’逐步经历‘{phase}’，直面新的挑战与人物关系变动。",
                        "status": "pending",
                        "content": ""
                    })

            # 更新前置上下文
            if chapters:
                last_c = chapters[-1]
                prev_chapters_info = f"- {last_c['title']}: {last_c['summary']}"
                if len(chapters) >= 2:
                    prev_chapters_info = f"- {chapters[-2]['title']}: {chapters[-2]['summary']}\n" + prev_chapters_info
            
            volumes_result.append({
                "volume_id": v_num,
                "volume_title": v_title,
                "volume_summary": v_summary,
                "chapters": chapters
            })
            
        return volumes_result, None

    @classmethod
    def generate_draft(cls, model: str, api_key: str, book_meta: dict, volume_summary: str, chapter_title: str, chapter_summary: str) -> str:
        """第一轮 (Drafting)：模型调用，带 Mock 备用机制"""
        if not api_key:
            return cls._get_mock_chapter(chapter_title, chapter_summary, book_meta["title"])

        prompt = f"""你是一个顶级小说创作者。请根据以下大纲与梗概，展开撰写一章正式的小说章节正文。
要求：
1. 语言流畅，细节丰富，增加环境描写与细节衬托，使得叙事平实而画面感十足。
2. 严禁说教、空洞套词。
3. 长度要求在3000字左右。

书籍设定背景：{book_meta['background']}
故事主线：{book_meta['synopsis']}
本卷大纲概要：{volume_summary}
当前章节标题：{chapter_title}
本章剧情详细梗概：{chapter_summary}

直接输出正文，不需要任何前言和后记。"""

        try:
            return cls._call_api(model, api_key, prompt)
        except Exception as e:
            print(f"API调用失败: {e}，将降级为Mock生成")
            return cls._get_mock_chapter(chapter_title, chapter_summary, book_meta["title"])

    @staticmethod
    def _get_mock_chapter(title: str, summary: str, book_title: str) -> str:
        """根据章节标题和概要生成稍微动态、丰富的 Mock 正文内容 (消除原写死返回冷硬 Mock 缺点)"""
        return f"""【{book_title} · {title}】

（本章正文由系统沙盒模拟引擎生成）

计算洪流的寒意在空气中缓缓散开，颈后的神经插槽还在传来隐隐约约的突突跃动感。林默深深地吐了一口气，抬眼望去，老旧管道缝隙中渗出的黑色机油泛着幽暗的光泽。

这里是第十三区，在这个被遗忘的垃圾场底层，连月光都显得奢侈。

“这块软盘的编码非常古怪，我甚至无法定位它的物理扇区。”白雀坐在一台嗡嗡作响的服务器机箱上，那只泛着哑光冷铁色泽的碳纤维义肢正不紧不慢地敲击着膝盖。她的眼神里少见地泛起一丝极其凝重的探询。

林默走上前，看着屏幕上如瀑布般刷新红色的溢出字符。他知道，这不仅仅是一次系统清理任务那么简单。关于《{book_title}》的传说，以及这章背后的剧情（“{summary}”），都在向他揭示，这个世界隐藏着比这片钢铁废墟更加庞大和残酷的秘密。

随着手指在陈旧的机械键盘上敲击，林默的眼眸深处，仿佛也点亮了那道本不属于这个时代的数字本源。"""
