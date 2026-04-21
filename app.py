"""
法语拐杖 (French Crutch) - Gradio Web App
目标用户：法语 0 基础自学者，目标 CEFR B1-B2
功能模块：发音、单词与短语、听写、语法、设置面板
"""

import json
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

import gradio as gr
import pandas as pd

# =============================================================================
# 配置与常量
# =============================================================================

# 文件路径（相对于项目根目录）
DATA_DIR = Path(__file__).parent / "data"
ASSETS_DIR = Path(__file__).parent / "assets"

LEXICON_PATH = DATA_DIR / "lexicon_sample.csv"
GRAMMAR_PATH = DATA_DIR / "grammar_questions_sample.json"
PHONEMES_PATH = DATA_DIR / "phonemes.json"

# 默认设置
DEFAULT_SETTINGS = {
    "language_mode": "A",  # A: 中法+英法, B: 纯中法
    "target_level": "B1",
    "daily_new_words": 10,
}

# 间隔重复简化版 SM-2 参数
SR_EASE_DEFAULT = 2.5
SR_INTERVAL_MIN = 1  # 最小间隔天数

# =============================================================================
# 数据加载（启动时一次性加载，避免运行时阻塞）
# =============================================================================

def load_data():
    """加载所有数据文件，返回字典"""
    data = {}
    
    # 加载词典
    if LEXICON_PATH.exists():
        data["lexicon"] = pd.read_csv(LEXICON_PATH)
    else:
        data["lexicon"] = pd.DataFrame()
    
    # 加载语法题库
    if GRAMMAR_PATH.exists():
        with open(GRAMMAR_PATH, "r", encoding="utf-8") as f:
            data["grammar"] = json.load(f)
    else:
        data["grammar"] = []
    
    # 加载音标数据
    if PHONEMES_PATH.exists():
        with open(PHONEMES_PATH, "r", encoding="utf-8") as f:
            data["phonemes"] = json.load(f)
    else:
        data["phonemes"] = []
    
    return data

# 全局数据缓存
DATA_CACHE = load_data()

# =============================================================================
# 间隔重复 (Spaced Repetition) 简化实现
# =============================================================================

def init_sr_state(word_ids):
    """初始化间隔重复状态字典"""
    return {
        wid: {
            "status": "new",  # new, learning, review, mastered
            "interval_days": 0,
            "next_review_date": None,
            "ease_factor": SR_EASE_DEFAULT,
            "review_count": 0,
        }
        for wid in word_ids
    }

def update_sr_status(sr_state, word_id, quality):
    """
    根据答题质量更新 SR 状态
    quality: 0-5 (0=完全不会, 5=完美掌握)
    简化版 SM-2 算法
    """
    if word_id not in sr_state:
        return sr_state
    
    state = sr_state[word_id]
    
    # 更新 ease factor
    new_ease = state["ease_factor"] + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    state["ease_factor"] = max(1.3, new_ease)  # 最小值 1.3
    
    if quality < 3:
        # 答错或模糊，重置间隔
        state["interval_days"] = SR_INTERVAL_MIN
        state["status"] = "learning"
    else:
        # 答对，增加间隔
        if state["review_count"] == 0:
            state["interval_days"] = 1
        elif state["review_count"] == 1:
            state["interval_days"] = 6
        else:
            state["interval_days"] = int(state["interval_days"] * state["ease_factor"])
        state["status"] = "review" if state["review_count"] < 3 else "mastered"
    
    state["review_count"] += 1
    state["next_review_date"] = (datetime.now() + timedelta(days=state["interval_days"])).strftime("%Y-%m-%d")
    
    return sr_state

def get_due_words(sr_state, today=None):
    """获取今天到期的复习单词"""
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    
    due = []
    for wid, state in sr_state.items():
        if state["next_review_date"] and state["next_review_date"] <= today:
            due.append(wid)
    return due

# =============================================================================
# 工具函数
# =============================================================================

def get_meaning_display(row, mode):
    """根据语言模式返回释义显示"""
    if mode == "B":  # 纯中法
        return f"{row['zh_meaning']}"
    else:  # 中法+英法
        return f"{row['zh_meaning']} | {row['en_meaning']}"

def get_explanation_display(explanation_zh, explanation_en, mode):
    """根据语言模式返回解析显示"""
    if mode == "B":
        return explanation_zh
    else:
        return f"【中文】{explanation_zh}\n【English】{explanation_en}"

# =============================================================================
# Gradio UI 构建
# =============================================================================

def create_app():
    """创建 Gradio 应用"""
    
    with gr.Blocks(title="法语拐杖 French Crutch", css="""
        .phoneme-btn { margin: 5px; }
        .meaning-text { font-size: 1.1em; line-height: 1.6; }
        .explanation-box { background: #f5f5f5; padding: 15px; border-radius: 8px; }
    """) as app:
        
        # =========================================================================
        # 全局状态
        # =========================================================================
        settings_state = gr.State(DEFAULT_SETTINGS.copy())
        sr_state = gr.State({})  # 间隔重复状态
        current_word_id = gr.State(None)  # 当前单词ID
        current_grammar_id = gr.State(None)  # 当前语法题ID
        
        # =========================================================================
        # 标题
        # =========================================================================
        gr.Markdown("""
        # 🇫🇷 法语拐杖 French Crutch
        **为法语 0 基础自学者设计的 CEFR B1-B2 学习工具**
        """)
        
        # =========================================================================
        # Tab 布局
        # =========================================================================
        with gr.Tabs():
            
            # =====================================================================
            # Tab 1: 设置面板
            # =====================================================================
            with gr.TabItem("⚙️ 设置"):
                gr.Markdown("### 全局学习设置")
                
                with gr.Row():
                    language_mode = gr.Radio(
                        choices=[("中法 + 英法", "A"), ("纯中法", "B")],
                        value="A",
                        label="语言辅助模式"
                    )
                    target_level = gr.Radio(
                        choices=["B1", "B2"],
                        value="B1",
                        label="目标等级"
                    )
                
                daily_new_words = gr.Slider(
                    minimum=5, maximum=50, step=5, value=10,
                    label="每日新学单词数量"
                )
                
                save_btn = gr.Button("保存设置", variant="primary")
                settings_msg = gr.Textbox(label="状态", interactive=False)
                
                def save_settings(mode, level, daily):
                    return {
                        "language_mode": mode,
                        "target_level": level,
                        "daily_new_words": daily,
                    }, "设置已保存！"
                
                save_btn.click(
                    save_settings,
                    inputs=[language_mode, target_level, daily_new_words],
                    outputs=[settings_state, settings_msg]
                )
            
            # =====================================================================
            # Tab 2: 发音
            # =====================================================================
            with gr.TabItem("🔊 发音"):
                gr.Markdown("### 法语音标学习")
                
                with gr.Row():
                    # 左侧：音标按钮列表
                    with gr.Column(scale=1):
                        gr.Markdown("**选择音标：**")
                        phoneme_buttons = []
                        phoneme_data_map = {p["symbol"]: p for p in DATA_CACHE["phonemes"]}
                        
                        for p in DATA_CACHE["phonemes"]:
                            btn = gr.Button(p["symbol"], size="sm", elem_classes=["phoneme-btn"])
                            phoneme_buttons.append((btn, p["symbol"]))
                    
                    # 右侧：音标详情
                    with gr.Column(scale=2):
                        phoneme_symbol = gr.Textbox(label="音标", interactive=False)
                        phoneme_desc = gr.Textbox(label="发音描述", interactive=False, lines=3)
                        phoneme_mouth = gr.Textbox(label="嘴型说明", interactive=False)
                        phoneme_similar = gr.Textbox(label="类比音", interactive=False, lines=2)
                        
                        # 音频播放
                        audio_player = gr.Audio(label="发音", type="filepath")
                        audio_status = gr.Textbox(label="音频状态", interactive=False)
                        
                        def show_phoneme(symbol):
                            p = phoneme_data_map.get(symbol, {})
                            
                            # 构建音频路径
                            audio_path = None
                            status_msg = "音频待补全"
                            if p.get("audio_files"):
                                audio_file = p["audio_files"][0]
                                full_path = ASSETS_DIR / "audio" / "phonemes" / audio_file
                                if full_path.exists():
                                    audio_path = str(full_path)
                                    status_msg = f"播放: {audio_file}"
                                else:
                                    status_msg = f"音频文件缺失: {audio_file}"
                            
                            return (
                                p.get("symbol", ""),
                                f"中文：{p.get('description_zh', '')}\nEnglish：{p.get('description_en', '')}",
                                p.get("mouth_shape_note", ""),
                                f"中文类比：{p.get('similar_sound_zh', '')}\nEnglish：{p.get('similar_sound_en', '')}",
                                audio_path,
                                status_msg
                            )
                        
                        # 绑定按钮事件
                        for btn, symbol in phoneme_buttons:
                            btn.click(
                                show_phoneme,
                                inputs=gr.State(symbol),
                                outputs=[phoneme_symbol, phoneme_desc, phoneme_mouth, phoneme_similar, audio_player, audio_status]
                            )
            
            # =====================================================================
            # Tab 3: 单词与短语
            # =====================================================================
            with gr.TabItem("📚 单词与短语"):
                gr.Markdown("### 背单词 + 间隔重复")
                
                with gr.Row():
                    # 左侧：学习模式选择
                    with gr.Column(scale=1):
                        vocab_mode = gr.Radio(
                            choices=[("选择题", "choice"), ("拼写模式", "spelling")],
                            value="choice",
                            label="学习模式"
                        )
                        start_vocab_btn = gr.Button("开始/下一题", variant="primary")
                        
                        # 背单词计划显示
                        gr.Markdown("---")
                        vocab_plan_info = gr.Textbox(
                            label="背单词计划",
                            interactive=False,
                            lines=4
                        )
                    
                    # 右侧：题目区域
                    with gr.Column(scale=2):
                        vocab_question = gr.Textbox(label="题目", interactive=False, lines=2)
                        vocab_options = gr.Radio(choices=[], label="选项", visible=False)
                        vocab_input = gr.Textbox(label="输入法语单词", visible=False)
                        vocab_submit = gr.Button("提交答案", visible=False)
                        vocab_result = gr.Textbox(label="结果", interactive=False)
                        vocab_explanation = gr.Textbox(label="解析", interactive=False, lines=3)
                
                def update_vocab_plan(settings):
                    """更新背单词计划显示"""
                    lexicon = DATA_CACHE["lexicon"]
                    if lexicon.empty:
                        return "暂无词汇数据"
                    
                    total_words = len(lexicon)
                    daily = settings["daily_new_words"]
                    
                    # 简化计算：假设每天学 daily 个新词
                    estimated_days = (total_words + daily - 1) // daily
                    finish_date = (datetime.now() + timedelta(days=estimated_days)).strftime("%Y-%m-%d")
                    
                    return f"""📊 词汇书统计
总词汇量: {total_words} 词
每日目标: {daily} 词
预计完成天数: {estimated_days} 天
预计完成日期: {finish_date}"""
                
                def generate_vocab_question(mode, settings, sr_state_val):
                    """生成单词题目"""
                    lexicon = DATA_CACHE["lexicon"]
                    if lexicon.empty:
                        return "暂无词汇数据", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), "", "", None, sr_state_val
                    
                    # 过滤目标等级
                    level = settings["target_level"]
                    level_words = lexicon[lexicon["level"].isin([level, "A1", "A2"])] if level == "B1" else lexicon
                    
                    if level_words.empty:
                        return "该等级暂无词汇", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), "", "", None, sr_state_val
                    
                    # 随机选择单词
                    row = level_words.sample(1).iloc[0]
                    word_id = str(row["id"])
                    
                    # 初始化 SR 状态
                    if word_id not in sr_state_val:
                        sr_state_val[word_id] = {
                            "status": "new",
                            "interval_days": 0,
                            "next_review_date": None,
                            "ease_factor": SR_EASE_DEFAULT,
                            "review_count": 0,
                        }
                    
                    if mode == "choice":
                        # 选择题模式
                        correct_meaning = get_meaning_display(row, settings["language_mode"])
                        
                        # 随机选 3 个干扰项
                        distractors = level_words[level_words["id"] != row["id"]].sample(min(3, len(level_words)-1))
                        wrong_meanings = [get_meaning_display(r, settings["language_mode"]) for _, r in distractors.iterrows()]
                        
                        options = wrong_meanings + [correct_meaning]
                        random.shuffle(options)
                        
                        question = f"【{row['pos']}】{row['lemma']}"
                        
                        return (
                            question,
                            gr.update(choices=options, visible=True, value=None),
                            gr.update(visible=False),
                            gr.update(visible=True),
                            "",
                            "",
                            word_id,
                            sr_state_val
                        )
                    else:
                        # 拼写模式
                        meaning = get_meaning_display(row, settings["language_mode"])
                        question = f"请拼写：{meaning}"
                        
                        return (
                            question,
                            gr.update(visible=False),
                            gr.update(visible=True, value=""),
                            gr.update(visible=True),
                            "",
                            "",
                            word_id,
                            sr_state_val
                        )
                
                def check_vocab_answer(user_answer, mode, word_id, settings, sr_state_val):
                    """检查单词答案"""
                    if word_id is None:
                        return "请先开始题目", "", sr_state_val
                    
                    lexicon = DATA_CACHE["lexicon"]
                    row = lexicon[lexicon["id"] == int(word_id)].iloc[0]
                    correct_lemma = row["lemma"].lower().strip()
                    
                    if mode == "choice":
                        # 选择题：从选项中找正确答案
                        correct_meaning = get_meaning_display(row, settings["language_mode"])
                        is_correct = user_answer == correct_meaning
                    else:
                        # 拼写模式
                        user_clean = user_answer.lower().strip()
                        is_correct = user_clean == correct_lemma
                    
                    # 更新 SR 状态
                    quality = 5 if is_correct else (3 if mode == "choice" and user_answer else 0)
                    sr_state_val = update_sr_status(sr_state_val, word_id, quality)
                    
                    # 构建反馈
                    example = f"例句：{row['example_fr']}\n{row['example_zh']}"
                    if is_correct:
                        result = f"✅ 正确！"
                    else:
                        result = f"❌ 错误。正确答案是：{row['lemma']}"
                    
                    explanation = f"{result}\n\n{example}"
                    
                    return result, explanation, sr_state_val
                
                # 绑定事件
                start_vocab_btn.click(
                    generate_vocab_question,
                    inputs=[vocab_mode, settings_state, sr_state],
                    outputs=[vocab_question, vocab_options, vocab_input, vocab_submit, vocab_result, vocab_explanation, current_word_id, sr_state]
                )
                
                vocab_submit.click(
                    check_vocab_answer,
                    inputs=[vocab_options if vocab_mode.value == "choice" else vocab_input, vocab_mode, current_word_id, settings_state, sr_state],
                    outputs=[vocab_result, vocab_explanation, sr_state]
                )
                
                # 初始化计划显示
                app.load(update_vocab_plan, inputs=settings_state, outputs=vocab_plan_info)
            
            # =====================================================================
            # Tab 4: 听写
            # =====================================================================
            with gr.TabItem("🎧 听写"):
                gr.Markdown("### 听写练习（简化版）")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        dictation_start = gr.Button("开始听写", variant="primary")
                        play_hint = gr.Textbox(
                            label="提示",
                            value="点击开始，然后输入你听到的单词",
                            interactive=False
                        )
                    
                    with gr.Column(scale=2):
                        dictation_input = gr.Textbox(label="输入你听到的单词")
                        dictation_submit = gr.Button("提交")
                        dictation_result = gr.Textbox(label="结果", interactive=False)
                        dictation_answer = gr.Textbox(label="正确答案", interactive=False)
                
                def start_dictation(settings, sr_state_val):
                    """开始听写"""
                    lexicon = DATA_CACHE["lexicon"]
                    if lexicon.empty:
                        return "暂无词汇", None, sr_state_val
                    
                    level = settings["target_level"]
                    level_words = lexicon[lexicon["level"].isin([level, "A1", "A2"])] if level == "B1" else lexicon
                    
                    if level_words.empty:
                        return "该等级暂无词汇", None, sr_state_val
                    
                    row = level_words.sample(1).iloc[0]
                    word_id = str(row["id"])
                    
                    # 初始化 SR
                    if word_id not in sr_state_val:
                        sr_state_val[word_id] = {
                            "status": "new",
                            "interval_days": 0,
                            "next_review_date": None,
                            "ease_factor": SR_EASE_DEFAULT,
                            "review_count": 0,
                        }
                    
                    hint = f"【{row['pos']}】听发音，输入单词"
                    return hint, word_id, sr_state_val
                
                def check_dictation(user_input, word_id, settings, sr_state_val):
                    """检查听写答案"""
                    if word_id is None:
                        return "请先开始", "", sr_state_val
                    
                    lexicon = DATA_CACHE["lexicon"]
                    row = lexicon[lexicon["id"] == int(word_id)].iloc[0]
                    correct = row["lemma"].lower().strip()
                    user_clean = user_input.lower().strip()
                    
                    is_correct = user_clean == correct
                    quality = 5 if is_correct else 2
                    sr_state_val = update_sr_status(sr_state_val, word_id, quality)
                    
                    result = "✅ 正确！" if is_correct else f"❌ 错误"
                    answer = f"{row['lemma']} - {get_meaning_display(row, settings['language_mode'])}"
                    
                    return result, answer, sr_state_val
                
                dictation_start.click(
                    start_dictation,
                    inputs=[settings_state, sr_state],
                    outputs=[play_hint, current_word_id, sr_state]
                )
                
                dictation_submit.click(
                    check_dictation,
                    inputs=[dictation_input, current_word_id, settings_state, sr_state],
                    outputs=[dictation_result, dictation_answer, sr_state]
                )
            
            # =====================================================================
            # Tab 5: 语法
            # =====================================================================
            with gr.TabItem("📝 语法"):
                gr.Markdown("### 语法练习（单选 + 填空）")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        grammar_start = gr.Button("下一题", variant="primary")
                        grammar_topic = gr.Textbox(label="语法点", interactive=False)
                        grammar_level = gr.Textbox(label="等级", interactive=False)
                    
                    with gr.Column(scale=2):
                        grammar_question = gr.Textbox(label="题目", interactive=False, lines=2)
                        grammar_options = gr.Radio(choices=[], label="选项", visible=False)
                        grammar_input = gr.Textbox(label="填空答案", visible=False)
                        grammar_submit = gr.Button("提交", visible=False)
                        grammar_result = gr.Textbox(label="结果", interactive=False)
                        grammar_explanation = gr.Textbox(label="解析", interactive=False, lines=4)
                
                def generate_grammar_question(settings):
                    """生成语法题"""
                    questions = DATA_CACHE["grammar"]
                    if not questions:
                        return "暂无题目", "", "", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), None, ""
                    
                    # 过滤等级
                    level = settings["target_level"]
                    level_qs = [q for q in questions if q["level"] in [level, "A1", "A2"]] if level == "B1" else questions
                    
                    if not level_qs:
                        return "该等级暂无题目", "", "", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), None, ""
                    
                    q = random.choice(level_qs)
                    
                    if q["question_type"] == "single_choice":
                        return (
                            q["grammar_topic"],
                            q["level"],
                            q["question_text"],
                            gr.update(choices=q.get("options", []), visible=True, value=None),
                            gr.update(visible=False),
                            gr.update(visible=True),
                            q["id"],
                            ""
                        )
                    else:
                        return (
                            q["grammar_topic"],
                            q["level"],
                            q["question_text"],
                            gr.update(visible=False),
                            gr.update(visible=True, value=""),
                            gr.update(visible=True),
                            q["id"],
                            ""
                        )
                
                def check_grammar_answer(user_answer, question_id, settings):
                    """检查语法答案"""
                    if question_id is None:
                        return "请先开始题目", ""
                    
                    questions = DATA_CACHE["grammar"]
                    q = next((x for x in questions if x["id"] == question_id), None)
                    
                    if q is None:
                        return "题目错误", ""
                    
                    correct = q["answer"].lower().strip()
                    user_clean = (user_answer or "").lower().strip()
                    
                    is_correct = user_clean == correct
                    result = "✅ 正确！" if is_correct else f"❌ 错误。正确答案是：{q['answer']}"
                    
                    explanation = get_explanation_display(
                        q.get("explanation_zh", ""),
                        q.get("explanation_en", ""),
                        settings["language_mode"]
                    )
                    
                    return result, explanation
                
                grammar_start.click(
                    generate_grammar_question,
                    inputs=[settings_state],
                    outputs=[grammar_topic, grammar_level, grammar_question, grammar_options, grammar_input, grammar_submit, current_grammar_id, grammar_result]
                )
                
                grammar_submit.click(
                    check_grammar_answer,
                    inputs=[grammar_options if True else grammar_input, current_grammar_id, settings_state],
                    outputs=[grammar_result, grammar_explanation]
                )
        
        # 页脚
        gr.Markdown("""
        ---
        *法语拐杖 v0.1 | 本地开发版 | 推送到 Hugging Face Space 使用*
        """)
    
    return app

# =============================================================================
# 启动入口
# =============================================================================

if __name__ == "__main__":
    app = create_app()
    # 使用 share=False 避免自动创建公开链接
    # 在 Hugging Face Space 上会自动使用正确的端口
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)