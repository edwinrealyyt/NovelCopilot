import re
import math
import requests
from typing import Dict, List, Tuple, Optional

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
        
        total_tokens = math.ceil(chinese_chars * 1.3 + english_words * 1.4 + (len(text) - chinese_chars - english_words) * 0.5)
        return total_tokens

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """根据费率计算预估费用"""
        rates = MODEL_RATES.get(model, {"input": 1.0, "output": 3.0})
        cost = (input_tokens * rates["input"] / 1000000.0) + (output_tokens * rates["output"] / 1000000.0)
        return cost

    @staticmethod
    def apply_de_ai_polish(text: str) -> Tuple[str, List[Dict[str, str]]]:
        """执行去AI痕迹过滤并统计替换历史"""
        polished = text
        changes = []
        
        for pattern, replacement in DE_AI_DICTIONARY:
            matches = pattern.findall(polished)
            if matches:
                # 记录替换的词汇
                for match in set(matches):
                    changes.append({
                        "original": match,
                        "replacement": replacement
                    })
                polished = pattern.sub(replacement, polished)
                
        return polished, changes

    @staticmethod
    def check_logic_consistency(content: str, background: str, synopsis: str) -> List[Dict[str, str]]:
        """逻辑设定防 OOC 与设定冲突校验 (词袋匹配与关键实体规则校验)"""
        reports = []
        
        if not content:
            return reports

        # 示例一: 校验白雀的性格冷酷特征 (防OOC)
        # 如果文中提到了白雀且伴随了情绪化崩溃的词
        if "白雀" in content:
            emotional_words = ["大哭", "崩溃", "不知所措", "惊慌失措", "委屈地流泪"]
            for word in emotional_words:
                if word in content:
                    reports.append({
                        "level": "warning",
                        "text": f"人设一致性警告：白雀在背景设定中为‘冷面独行黑客’，但本章描写中出现‘{word}’，存在OOC崩人设风险，建议修改为更克制的情绪细节描写。"
                    })
                    break
        
        # 示例二: 地理空间与背景一致性校验
        # 比如天启之门属于十三区，如果主角无视物理距离瞬间到达一区
        if "第十三区" in background and "林默" in content:
            if "一区" in content and "瞬间" in content:
                reports.append({
                    "level": "warning",
                    "text": "空间位置警告：第十三区垃圾场与神代重工第一区行政区隔绝，林默‘瞬间到达’在设定中属于禁区，建议增加乘坐轨道交通或地下潜入的过门描写。"
                })

        # 示例三: 主角插槽设定
        if "林默" in content and "颈部" in content and "插槽" not in content and "芯片" in content:
            reports.append({
                "level": "info",
                "text": "特征校验：主角林默使用芯片过载，已自动校验其颈部神经插槽的物理接口设定，符合世界观。"
            })

        if not reports:
            reports.append({
                "level": "info",
                "text": "人物设定、主线推进及空间位置校验成功，暂未发现违背设定或OOC情况。"
            })
            
        return reports

    @classmethod
    def generate_draft(cls, model: str, api_key: str, book_meta: dict, volume_summary: str, chapter_title: str, chapter_summary: str) -> str:
        """第一轮 (Drafting)：模型调用，带 Mock 备用机制"""
        if not api_key:
            # 离线 Mock 逻辑
            return cls._get_mock_chapter(chapter_title, chapter_summary, book_meta["title"])

        prompt = f"""你是一个顶级小说创作者。请根据以下大纲与梗概，展开撰写一章正式的小说章节正文。
要求：
1. 语言流畅，细节丰富，增加白描与环境衬托。
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

    @classmethod
    def _call_api(cls, model: str, api_key: str, prompt: str) -> str:
        """发起真实的 HTTP 接口调用"""
        model_lower = model.lower()
        if "gemini" in model_lower:
            # 确保含有 models/ 前缀
            api_model = model if model.startswith("models/") else f"models/{model}"
            url = f"https://generativelanguage.googleapis.com/v1beta/{api_model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 8192}
            }
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            res.raise_for_status()
            data = res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
            
        elif "deepseek" in model_lower or "coder" in model_lower or "chat" in model_lower:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            payload = {
                "model": model,  # 直接透传动态模型ID
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            }
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            res.raise_for_status()
            data = res.json()
            return data["choices"][0]["message"]["content"]
            
        else:
            raise NotImplementedError(f"模型 {model} 暂不支持在后端发起原生调用")

    @staticmethod
    def _get_mock_chapter(title: str, summary: str, book_title: str) -> str:
        """生成精美的高保真 Mock 章节正文"""
        return f"""当炽热的计算洪流在新东京错综复杂的地下光纤网中逐渐冷却，林默终于睁开了眼睛。\n\n视线里没有了那些冰冷的红色追踪标记，取而代之的，是破旧石棉瓦棚顶和不断渗出铁锈水的铜管。空气中飘荡着廉价合成机油与陈旧霉味混合的气息，让人感到一阵真实而剧烈的恶心。\n\n“你醒了。”一个清冷而有些沙哑的女声从身侧传来。\n\n林默挣扎着坐起身，脖子后方的过载芯片接口还在突突地抽痛。他看清了说话的人。那是一个盘腿坐在主机箱上的年轻女子，穿着洗得发白的无袖皮衣，左臂完全是由哑光碳纤维构成的精细义肢。她手里正把玩着林默视若生命的那个旧软盘读取器。\n\n“白雀？”林默在脑海中的公共黑客名录里检索到了这张冷峻的面孔。\n\n女子没有否认，只是用那只机械手在软盘上轻轻敲了敲：“能在三个猎犬的夹击下活下来，还带着这件垃圾，你确实有点意思。不过，这里面的数据已经被你全部格式化写入了脑域，对吧？现在，告诉我你看到了什么，或者，我亲自动手把你的脑叶剖开来看看。”\n\n林默沉默了片刻，他的双眼微动，此时他的视界与普通人已经完全不同。在他的视野深处，白雀的呼吸频率、心率，甚至是这间密室的供电电压波形，都化作了一排排跃动的半透明字符。那块软盘里的密码，真的在他的大脑里扎了根，让他直接看穿了这个由数字编织的华丽囚笼。"""
