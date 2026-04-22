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

# 每日进度默认值（跨天自动重置）
DEFAULT_DAILY_PROGRESS = {
    "date": "",       # "YYYY-MM-DD"
    "new_words_today": 0,
    "reviewed_today": 0,
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
    """获取今天到期的复习单词（next_review_date <= today）"""
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    due = []
    for wid, state in sr_state.items():
        if (state["next_review_date"] and
                state["next_review_date"] <= today and
                state["status"] not in ("new", "mastered")):
            due.append(wid)
    return due

# =============================================================================
# SR 选词辅助函数（模块级，供 generate_vocab_question 调用）
# =============================================================================

def _get_new_word_candidates(lexicon_df, sr_state, level, daily_limit, new_words_today):
    """
    筛选出可作为「新词」候选的单词：
    - 不在 sr_state 中（即从未被学习过）
    - 或在 sr_state 中但从未回答过（review_count == 0 且 next_review_date 为 None）
    受到每日限额约束
    """
    remaining = daily_limit - new_words_today
    if remaining <= 0:
        return []

    candidates = []
    for _, row in lexicon_df.iterrows():
        wid = str(row["id"])
        if wid in sr_state:
            state = sr_state[wid]
            # 已初始化过且回答过的（哪怕只复习过一次）→ 不算新词
            if state["review_count"] > 0:
                continue
        candidates.append(row)

    random.shuffle(candidates)
    return candidates[:remaining]


def _filter_level(lexicon_df, target_level):
    """按目标等级过滤词汇"""
    if target_level == "B1":
        return lexicon_df[lexicon_df["level"].isin([target_level, "A1", "A2"])]
    else:
        return lexicon_df

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
        sr_state = gr.State({})            # 间隔重复状态 {word_id: {...}}
        daily_progress = gr.State(DEFAULT_DAILY_PROGRESS.copy())  # 每日进度
        current_word_id = gr.State(None)    # 当前单词ID
        current_grammar_id = gr.State(None) # 当前语法题ID
        vocab_mode_state = gr.State("choice")  # 当前单词模式（用于 answer check）

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
                            label="今日进度",
                            interactive=False,
                            lines=5
                        )

                    # 右侧：题目区域
                    with gr.Column(scale=2):
                        vocab_question = gr.Textbox(label="题目", interactive=False, lines=2)
                        vocab_options = gr.Radio(choices=[], label="选项", visible=False)
                        vocab_input = gr.Textbox(label="输入法语单词", visible=False)
                        vocab_submit = gr.Button("提交答案", visible=False)
                        vocab_result = gr.Textbox(label="结果", interactive=False)
                        vocab_explanation = gr.Textbox(label="解析", interactive=False, lines=3)

                def update_vocab_plan(settings, progress):
                    """更新今日学习进度显示"""
                    today_str = datetime.now().strftime("%Y-%m-%d")

                    # 跨天重置
                    if progress["date"] != today_str:
                        progress = {
                            "date": today_str,
                            "new_words_today": 0,
                            "reviewed_today": 0,
                        }

                    lexicon = DATA_CACHE["lexicon"]
                    if lexicon.empty:
                        return "暂无词汇数据", progress

                    level = settings["target_level"]
                    level_df = _filter_level(lexicon, level)
                    total_level = len(level_df)

                    # 统计已初始化过的单词数
                    started = sum(
                        1 for wid in (str(w) for w in level_df["id"])
                        if wid in DATA_CACHE.get("_sr_pool", {})
                    )
                    started = len([w for w in level_df["id"].astype(str)
                                   if w in DATA_CACHE.get("_sr_pool", {})])

                    due = get_due_words(DATA_CACHE.get("_sr_pool", {}), today_str)

                    daily = settings["daily_new_words"]
                    new_done = progress["new_words_today"]
                    new_left = max(0, daily - new_done)
                    reviewed = progress["reviewed_today"]

                    remaining = total_level - started

                    lines = [
                        f"📅 {today_str}",
                        f"✅ 今日新词: {new_done}/{daily}",
                        f"🔄 待复习: {len(due)} 词",
                        f"📚 本级词汇: {total_level} 词",
                    ]
                    if new_left > 0:
                        lines.append(f"💡 今日还可学新词: {new_left} 个")
                    else:
                        lines.append("🎉 今日新词任务已完成")

                    return "\n".join(lines), progress

                # -----------------------------------------------------------------
                # 核心重构：generate_vocab_question
                # -----------------------------------------------------------------
                def generate_vocab_question(mode, settings, sr_state_val, daily_progress_val):
                    """
                    SR 驱动的选词逻辑：
                    1. 优先抽取 due_words（待复习词汇）
                    2. 无复习词 → 抽取新词（受每日限额约束）
                    3. 两者均无 → 提示今日任务完成
                    """
                    today_str = datetime.now().strftime("%Y-%m-%d")

                    # 跨天重置每日进度
                    if daily_progress_val["date"] != today_str:
                        daily_progress_val = {
                            "date": today_str,
                            "new_words_today": 0,
                            "reviewed_today": 0,
                        }
                        sr_state_val = {}  # 可选：是否跨天清空 SR 由需求决定

                    lexicon = DATA_CACHE["lexicon"]
                    if lexicon.empty:
                        return (
                            "暂无词汇数据",
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            "",
                            "",
                            None,
                            sr_state_val,
                            daily_progress_val,
                            "choice"
                        )

                    level = settings["target_level"]
                    level_words = _filter_level(lexicon, level)

                    # 同步 sr_state_val 到全局缓存（供 update_vocab_plan 中的 get_due_words 使用）
                    DATA_CACHE["_sr_pool"] = sr_state_val

                    # -----------------------------------------------------------------
                    # 优先级 1：复习词（get_due_words）
                    # -----------------------------------------------------------------
                    due_ids = get_due_words(sr_state_val, today_str)
                    due_ids_filtered = [wid for wid in due_ids
                                        if str(wid) in level_words["id"].astype(str).values]

                    if due_ids_filtered:
                        # 随机抽取一个复习词
                        chosen_id = random.choice(due_ids_filtered)
                        row = level_words[level_words["id"].astype(str) == chosen_id].iloc[0]

                        # 初始化 SR 状态（如有必要）
                        if chosen_id not in sr_state_val:
                            sr_state_val[chosen_id] = {
                                "status": "new",
                                "interval_days": 0,
                                "next_review_date": None,
                                "ease_factor": SR_EASE_DEFAULT,
                                "review_count": 0,
                            }

                        word_id = chosen_id
                        word_type = "review"
                    else:
                        # -----------------------------------------------------------------
                        # 优先级 2：新词（受每日限额约束）
                        # -----------------------------------------------------------------
                        daily_limit = settings["daily_new_words"]
                        new_words_today = daily_progress_val["new_words_today"]

                        new_candidates = _get_new_word_candidates(
                            level_words, sr_state_val, level,
                            daily_limit, new_words_today
                        )

                        if new_candidates:
                            row = new_candidates[0]
                            word_id = str(row["id"])

                            # 初始化 SR 状态
                            sr_state_val[word_id] = {
                                "status": "new",
                                "interval_days": 0,
                                "next_review_date": None,
                                "ease_factor": SR_EASE_DEFAULT,
                                "review_count": 0,
                            }

                            # 消耗一个新词配额
                            daily_progress_val["new_words_today"] += 1
                            word_type = "new"
                        else:
                            # -----------------------------------------------------------------
                            # 优先级 3：今日任务全部完成
                            # -----------------------------------------------------------------
                            return (
                                "🎉 恭喜！今日学习任务已完成\n\n"
                                "✅ 新词目标达成\n"
                                "🔄 暂无待复习词汇\n\n"
                                "明天再来，继续加油！💪",
                                gr.update(visible=False),
                                gr.update(visible=False),
                                gr.update(visible=False),
                                "",
                                "",
                                None,
                                sr_state_val,
                                daily_progress_val,
                                mode
                            )

                    # -----------------------------------------------------------------
                    # 生成题目 UI
                    # -----------------------------------------------------------------
                    DATA_CACHE["_sr_pool"] = sr_state_val

                    if mode == "choice":
                        correct_meaning = get_meaning_display(row, settings["language_mode"])

                        # 干扰项：从同等级词汇中排除当前词后随机选 3 个
                        distractors = level_words[level_words["id"].astype(str) != word_id].sample(
                            min(3, len(level_words) - 1)
                        )
                        wrong_meanings = [
                            get_meaning_display(r, settings["language_mode"])
                            for _, r in distractors.iterrows()
                        ]

                        options = wrong_meanings + [correct_meaning]
                        random.shuffle(options)

                        type_tag = "🔄" if word_type == "review" else "🆕"
                        question = f"{type_tag}【{row['pos']}】{row['lemma']}"

                        return (
                            question,
                            gr.update(choices=options, visible=True, value=None),
                            gr.update(visible=False),
                            gr.update(visible=True),
                            "",
                            "",
                            word_id,
                            sr_state_val,
                            daily_progress_val,
                            mode
                        )
                    else:
                        meaning = get_meaning_display(row, settings["language_mode"])
                        type_tag = "🔄" if word_type == "review" else "🆕"
                        question = f"{type_tag} 请拼写：{meaning}"

                        return (
                            question,
                            gr.update(visible=False),
                            gr.update(visible=True, value=""),
                            gr.update(visible=True),
                            "",
                            "",
                            word_id,
                            sr_state_val,
                            daily_progress_val,
                            mode
                        )

                # -----------------------------------------------------------------
                # check_vocab_answer（统一处理两种模式）
                # -----------------------------------------------------------------
                def check_vocab_answer(radio_val, text_val, mode, word_id, settings, sr_state_val, daily_progress_val):
                    """检查单词答案（mode 参数决定使用哪个输入）"""
                    if word_id is None:
                        return "请先开始题目", "", sr_state_val, daily_progress_val

                    # 根据 mode 选择用户输入
                    user_answer = radio_val if mode == "choice" else text_val

                    lexicon = DATA_CACHE["lexicon"]
                    row = lexicon[lexicon["id"].astype(str) == str(word_id)].iloc[0]
                    correct_lemma = row["lemma"].lower().strip()

                    if mode == "choice":
                        correct_meaning = get_meaning_display(row, settings["language_mode"])
                        is_correct = user_answer == correct_meaning
                    else:
                        user_clean = (user_answer or "").lower().strip()
                        is_correct = user_clean == correct_lemma

                    # 更新 SR 状态
                    quality = 5 if is_correct else (0 if mode == "spelling" else 3)
                    sr_state_val = update_sr_status(sr_state_val, word_id, quality)

                    # 标记已复习
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    if daily_progress_val["date"] != today_str:
                        daily_progress_val = {
                            "date": today_str,
                            "new_words_today": 0,
                            "reviewed_today": 0,
                        }
                    daily_progress_val["reviewed_today"] += 1

                    # 构建反馈
                    example = f"例句：{row['example_fr']}\n{row['example_zh']}"
                    if is_correct:
                        result = "✅ 正确！"
                    else:
                        result = f"❌ 错误。正确答案是：{row['lemma']}"

                    explanation = f"{result}\n\n{example}"

                    DATA_CACHE["_sr_pool"] = sr_state_val

                    return result, explanation, sr_state_val, daily_progress_val

                # 模式切换 → 更新 vocab_mode_state
                vocab_mode.change(
                    lambda m: m,
                    inputs=[vocab_mode],
                    outputs=[vocab_mode_state]
                )

                # 点击开始 → 触发选词
                start_vocab_btn.click(
                    generate_vocab_question,
                    inputs=[vocab_mode, settings_state, sr_state, daily_progress],
                    outputs=[
                        vocab_question,
                        vocab_options, vocab_input, vocab_submit,
                        vocab_result, vocab_explanation,
                        current_word_id,
                        sr_state,
                        daily_progress,
                        vocab_mode_state,
                    ]
                )

                # 提交答案 → 检查（始终传入两个输入，由函数内部根据 mode 决定用哪个）
                vocab_submit.click(
                    check_vocab_answer,
                    inputs=[
                        vocab_options, vocab_input,
                        vocab_mode_state, current_word_id,
                        settings_state, sr_state, daily_progress
                    ],
                    outputs=[vocab_result, vocab_explanation, sr_state, daily_progress]
                )

                # 初始化进度显示
                app.load(
                    update_vocab_plan,
                    inputs=[settings_state, daily_progress],
                    outputs=[vocab_plan_info, daily_progress]
                )

            # =====================================================================
            # Tab 4: 听写
            # =====================================================================
            with gr.TabItem("🎧 听写"):
                gr.Markdown("### 听写练习（仅限复习词汇）")

                with gr.Row():
                    with gr.Column(scale=1):
                        dictation_start = gr.Button("开始听写", variant="primary")
                        play_hint = gr.Textbox(
                            label="提示",
                            value="点击开始，然后输入你听到的单词",
                            interactive=False
                        )
                        dictation_stats = gr.Textbox(
                            label="听写统计",
                            interactive=False,
                            lines=3
                        )

                    with gr.Column(scale=2):
                        dictation_input = gr.Textbox(label="输入你听到的单词")
                        dictation_submit = gr.Button("提交")
                        dictation_result = gr.Textbox(label="结果", interactive=False)
                        dictation_answer = gr.Textbox(label="正确答案", interactive=False)

                # -----------------------------------------------------------------
                # 核心重构：start_dictation
                # -----------------------------------------------------------------
                def start_dictation(settings, sr_state_val, daily_progress_val):
                    """
                    听写选词逻辑：
                    - 仅从 get_due_words（今日到期复习词汇）中抽取
                    - due_words 为空 → 提示无复习任务
                    """
                    today_str = datetime.now().strftime("%Y-%m-%d")

                    # 跨天重置（同步）
                    if daily_progress_val["date"] != today_str:
                        daily_progress_val = {
                            "date": today_str,
                            "new_words_today": 0,
                            "reviewed_today": 0,
                        }

                    lexicon = DATA_CACHE["lexicon"]
                    if lexicon.empty:
                        return "暂无词汇", None, "", sr_state_val, daily_progress_val

                    level = settings["target_level"]
                    level_words = _filter_level(lexicon, level)

                    # 仅从到期词汇中选
                    due_ids = get_due_words(sr_state_val, today_str)
                    due_in_level = [
                        wid for wid in due_ids
                        if str(wid) in level_words["id"].astype(str).values
                    ]

                    if not due_in_level:
                        # 无复习词
                        stats = (
                            f"📅 {today_str}\n"
                            f"🔄 待复习: 0 词\n"
                            f"✅ 新词听写需先在「单词」模块学习"
                        )
                        return (
                            "📭 今日暂无需要复习听写的单词\n\n"
                            "💡 请先在「单词与短语」模块完成今日学习计划，\n"
                            "    复习词积累后即可开始听写练习。",
                            None,
                            stats,
                            sr_state_val,
                            daily_progress_val
                        )

                    # 随机抽取一个到期词汇
                    chosen_id = random.choice(due_in_level)
                    row = level_words[level_words["id"].astype(str) == str(chosen_id)].iloc[0]

                    # 确保 SR 状态存在
                    if str(chosen_id) not in sr_state_val:
                        sr_state_val[str(chosen_id)] = {
                            "status": "new",
                            "interval_days": 0,
                            "next_review_date": None,
                            "ease_factor": SR_EASE_DEFAULT,
                            "review_count": 0,
                        }

                    hint = f"【{row['pos']}】听发音，输入单词"
                    stats = (
                        f"📅 {today_str}\n"
                        f"🔄 待复习: {len(due_in_level)} 词\n"
                        f"📝 当前: {row['lemma']}"
                    )

                    return hint, str(chosen_id), stats, sr_state_val, daily_progress_val

                # -----------------------------------------------------------------
                # check_dictation
                # -----------------------------------------------------------------
                def check_dictation(user_input, word_id, settings, sr_state_val, daily_progress_val):
                    """检查听写答案"""
                    if word_id is None:
                        return "请先开始", "", sr_state_val, daily_progress_val

                    lexicon = DATA_CACHE["lexicon"]
                    row = lexicon[lexicon["id"].astype(str) == str(word_id)].iloc[0]
                    correct = row["lemma"].lower().strip()
                    user_clean = (user_input or "").lower().strip()

                    is_correct = user_clean == correct
                    quality = 5 if is_correct else 2
                    sr_state_val = update_sr_status(sr_state_val, word_id, quality)

                    # 标记已复习
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    if daily_progress_val["date"] != today_str:
                        daily_progress_val = {
                            "date": today_str,
                            "new_words_today": 0,
                            "reviewed_today": 0,
                        }
                    daily_progress_val["reviewed_today"] += 1

                    result = "✅ 正确！" if is_correct else "❌ 错误"
                    answer = f"{row['lemma']} - {get_meaning_display(row, settings['language_mode'])}"

                    return result, answer, sr_state_val, daily_progress_val

                dictation_start.click(
                    start_dictation,
                    inputs=[settings_state, sr_state, daily_progress],
                    outputs=[play_hint, current_word_id, dictation_stats, sr_state, daily_progress]
                )

                dictation_submit.click(
                    check_dictation,
                    inputs=[dictation_input, current_word_id, settings_state, sr_state, daily_progress],
                    outputs=[dictation_result, dictation_answer, sr_state, daily_progress]
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
                        return (
                            "暂无题目",
                            "", "",
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            None,
                            ""
                        )

                    # 过滤等级
                    level = settings["target_level"]
                    level_qs = (
                        [q for q in questions if q["level"] in [level, "A1", "A2"]]
                        if level == "B1" else questions
                    )

                    if not level_qs:
                        return (
                            "该等级暂无题目",
                            "", "",
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            None,
                            ""
                        )

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
                    outputs=[
                        grammar_topic, grammar_level, grammar_question,
                        grammar_options, grammar_input, grammar_submit,
                        current_grammar_id, grammar_result
                    ]
                )

                grammar_submit.click(
                    check_grammar_answer,
                    inputs=[grammar_options, current_grammar_id, settings_state],
                    outputs=[grammar_result, grammar_explanation]
                )

        # 页脚
        gr.Markdown("""
        ---
        *法语拐杖 v0.2 | SR-driven learning | 本地开发版*
        """)

    return app

# =============================================================================
# 启动入口
# =============================================================================

if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
