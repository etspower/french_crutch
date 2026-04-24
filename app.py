"""
法语拐杖 (French Crutch) - Gradio Web App
目标用户：法语 0 基础自学者，目标 CEFR B1-B2
功能模块：发音、单词与短语、听写、语法、设置面板、进度持久化
"""

import json
import random
import os
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from gtts import gTTS

import gradio as gr
import pandas as pd

# =============================================================================
# 配置与常量
# =============================================================================

DATA_DIR     = Path(__file__).parent / "data"
ASSETS_DIR   = Path(__file__).parent / "assets"

LEXICON_PATH    = DATA_DIR / "lexicon_sample.csv"
GRAMMAR_PATH     = DATA_DIR / "grammar_questions_sample.json"
PHONEMES_PATH    = DATA_DIR / "phonemes.json"

DEFAULT_SETTINGS = {
    "language_mode":    "A",
    "target_level":     "B1",
    "daily_new_words":  10,
}

DEFAULT_DAILY_PROGRESS = {
    "date":             "",
    "new_words_today":  0,
    "reviewed_today":   0,
}

SR_EASE_DEFAULT   = 2.5
SR_INTERVAL_MIN   = 1

# =============================================================================
# 数据加载
# =============================================================================

def load_data():
    data = {}

    if LEXICON_PATH.exists():
        df = pd.read_csv(LEXICON_PATH)
        df.fillna("", inplace=True)
        data["lexicon"] = df
    else:
        data["lexicon"] = pd.DataFrame(columns=[
            "id", "lemma", "pos", "level",
            "zh_meaning", "en_meaning",
            "example_fr", "example_zh", "example_en"
        ])

    if GRAMMAR_PATH.exists():
        with open(GRAMMAR_PATH, "r", encoding="utf-8") as f:
            data["grammar"] = json.load(f)
    else:
        data["grammar"] = []

    if PHONEMES_PATH.exists():
        with open(PHONEMES_PATH, "r", encoding="utf-8") as f:
            data["phonemes"] = json.load(f)
    else:
        data["phonemes"] = []

    return data

DATA_CACHE = load_data()

# =============================================================================
# 间隔重复
# =============================================================================

def init_sr_state(word_ids):
    return {
        wid: {
            "status":         "new",
            "interval_days":   0,
            "next_review_date": None,
            "ease_factor":    SR_EASE_DEFAULT,
            "review_count":   0,
        }
        for wid in word_ids
    }

def update_sr_status(sr_state, word_id, quality):
    if word_id not in sr_state:
        return sr_state

    state = sr_state[word_id]

    new_ease = (state["ease_factor"]
                + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    state["ease_factor"] = max(1.3, new_ease)

    if quality < 3:
        state["interval_days"] = SR_INTERVAL_MIN
        state["status"]        = "learning"
    else:
        if state["review_count"] == 0:
            state["interval_days"] = 1
        elif state["review_count"] == 1:
            state["interval_days"] = 6
        else:
            state["interval_days"] = int(
                state["interval_days"] * state["ease_factor"]
            )
        state["status"] = "review" if state["review_count"] < 3 else "mastered"

    state["review_count"] += 1
    state["next_review_date"] = (
        datetime.now(timezone(timedelta(hours=8))) + timedelta(days=state["interval_days"])
    ).strftime("%Y-%m-%d")

    return sr_state

def get_due_words(sr_state, today=None):
    if today is None:
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    return [
        wid for wid, state in sr_state.items()
        if (state["next_review_date"]
            and state["next_review_date"] <= today
            and state["status"] not in ("new", "mastered"))
    ]

# =============================================================================
# 辅助函数
# =============================================================================

def _get_new_word_candidates(lexicon_df, sr_state, daily_limit, new_words_today):
    remaining = daily_limit - new_words_today
    if remaining <= 0:
        return []

    candidates = []
    for _, row in lexicon_df.iterrows():
        wid = str(row["id"])
        if wid in sr_state and sr_state[wid]["review_count"] > 0:
            continue
        candidates.append(row)

    random.shuffle(candidates)
    return candidates[:remaining]

def _filter_level(lexicon_df, target_level):
    if target_level == "B1":
        return lexicon_df[lexicon_df["level"].isin([target_level, "A1", "A2"])]
    return lexicon_df

def get_meaning_display(row, mode):
    if mode == "B":
        return str(row["zh_meaning"])
    return f"{row['zh_meaning']} | {row['en_meaning']}"

def get_explanation_display(explanation_zh, explanation_en, mode):
    if mode == "B":
        return explanation_zh
    return f"【中文】{explanation_zh}\n【English】{explanation_en}"

def _cross_day_reset(progress):
    today_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    if progress["date"] != today_str:
        return {"date": today_str, "new_words_today": 0, "reviewed_today": 0}
    return progress

def strip_accents(text):
    if not text: return ""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

# =============================================================================
# 进度持久化
# =============================================================================

def export_progress(sr_state, daily_progress, settings):
    payload = {
        "version":        1,
        "exported_at":    datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "sr_state":       sr_state,
        "daily_progress": daily_progress,
        "settings":       settings,
    }
    json_str = json.dumps(payload, ensure_ascii=False, indent=2)

    try:
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", prefix="french_crutch_progress_", mode="w", encoding="utf-8")
        tmp_file.write(json_str)
        tmp_file.close()
        tmp_path = tmp_file.name
    except Exception:
        raise

    return tmp_path

def import_progress(file_obj):
    if file_obj is None:
        return None, None, None, "❌ 未选择文件"

    payload = None
    try:
        # First try to process it as a file-like object
        if hasattr(file_obj, "seek") and hasattr(file_obj, "read"):
            file_obj.seek(0)
            payload = json.load(file_obj)
    except Exception:
        pass

    if payload is None:
        try:
            if isinstance(file_obj, dict):
                path = file_obj.get("name") or file_obj.get("file")
            else:
                path = str(file_obj)

            if not path or not os.path.exists(path):
                return None, None, None, "❌ 文件不存在或路径无效"

            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except json.JSONDecodeError:
            return None, None, None, "❌ 文件不是有效的 JSON 格式"
        except Exception as exc:
            return None, None, None, f"❌ 导入失败: {exc}"

    if not isinstance(payload, dict):
        return None, None, None, "❌ 文件内容格式不正确"

    sr_state       = payload.get("sr_state", {})
    daily_progress = payload.get("daily_progress", DEFAULT_DAILY_PROGRESS.copy())

    if not isinstance(sr_state, dict):
        return None, None, None, "❌ sr_state 格式错误"
    if not isinstance(daily_progress, dict):
        return None, None, None, "❌ daily_progress 格式错误"

    settings_from_file = payload.get("settings", {})
    if not isinstance(settings_from_file, dict):
        settings_from_file = {}
    settings = {**DEFAULT_SETTINGS, **settings_from_file}

    word_count = len(sr_state)
    msg = (f"✅ 导入成功！\n"
           f"📚 已加载 {word_count} 条学习记录\n"
           f"📅 上次学习日期: {daily_progress.get('date', '未知')}")

    return sr_state, daily_progress, settings, msg

# =============================================================================
# Gradio UI
# =============================================================================

def create_app():

    with gr.Blocks(title="法语拐杖 French Crutch", css="""
        .phoneme-btn { margin: 5px; }
        .meaning-text { font-size: 1.1em; line-height: 1.6; }
        .explanation-box { background: #f5f5f5; padding: 15px; border-radius: 8px; }
    """) as app:

        # 全局状态
        settings_state            = gr.State(DEFAULT_SETTINGS.copy())
        sr_state                  = gr.State({})
        daily_progress            = gr.State(DEFAULT_DAILY_PROGRESS.copy())
        current_word_id           = gr.State(None)
        current_grammar_id        = gr.State(None)
        current_grammar_qtype     = gr.State(None)
        vocab_mode_state          = gr.State("choice")

        # -------------------------------------------------------------------------
        # 标题
        # -------------------------------------------------------------------------
        gr.Markdown("""
        # 🇫🇷 法语拐杖 French Crutch
        **为法语 0 基础自学者设计的 CEFR B1-B2 学习工具**
        """)

        with gr.Tabs():

            # =========================================================================
            # Tab 1: 设置
            # =========================================================================
            with gr.TabItem("⚙️ 设置"):
                gr.Markdown("### 全局学习设置")

                with gr.Row():
                    language_mode = gr.Radio(
                        choices=[("中法 + 英法", "A"), ("纯中法", "B")],
                        value="A", label="语言辅助模式"
                    )
                    target_level = gr.Radio(
                        choices=["B1", "B2"],
                        value="B1", label="目标等级"
                    )

                daily_new_words = gr.Slider(
                    minimum=5, maximum=50, step=5, value=10,
                    label="每日新学单词数量"
                )

                save_btn    = gr.Button("保存设置", variant="primary")
                settings_msg = gr.Textbox(label="状态", interactive=False)

                def save_settings(mode, level, daily):
                    return {
                        "language_mode":   mode,
                        "target_level":    level,
                        "daily_new_words": daily,
                    }, "设置已保存！"

                save_btn.click(
                    save_settings,
                    inputs=[language_mode, target_level, daily_new_words],
                    outputs=[settings_state, settings_msg]
                )

                # -- 数据管理区块 -------------------------------------------------------
                gr.Markdown("---")
                gr.Markdown("### 💾 数据管理")

                with gr.Row():
                    # [修复 1] 拆分 DownloadButton 为两步
                    prepare_export_btn = gr.Button(
                        "📦 生成并准备导出", size="sm"
                    )
                    export_btn = gr.DownloadButton(
                        label="📥 点击下载进度文件",
                        visible=False,
                        size="sm"
                    )
                    import_btn = gr.UploadButton(
                        label="📥 导入学习进度",
                        file_types=[".json"], size="sm"
                    )

                import_msg = gr.Textbox(
                    label="导入结果", interactive=False, lines=2
                )

                # [修复 1] on_export_click 返回 gr.update 以控制 DownloadButton 显示
                def on_export_click(sr, progress, settings):
                    try:
                        path = export_progress(sr, progress, settings)
                        return gr.update(value=path, visible=True)
                    except Exception:
                        return gr.update(visible=False)

                def on_import_click(file_obj):
                    sr, prog, sett, msg = import_progress(file_obj)
                    if sr is None:
                        return (
                            None, None, None, msg,
                            gr.update(), gr.update(), gr.update()
                        )
                    return (
                        sr, prog, sett, msg,
                        gr.update(value=sett["language_mode"]),
                        gr.update(value=sett["target_level"]),
                        gr.update(value=sett.get("daily_new_words", 10)),
                    )

                # [修复 1] 绑定 prepare_export_btn 而不是 export_btn
                prepare_export_btn.click(
                    on_export_click,
                    inputs=[sr_state, daily_progress, settings_state],
                    outputs=[export_btn]
                )

                import_btn.upload(
                    on_import_click,
                    inputs=[],
                    outputs=[
                        sr_state, daily_progress, settings_state, import_msg,
                        language_mode, target_level, daily_new_words
                    ]
                )

            # =========================================================================
            # Tab 2: 发音
            # =========================================================================
            with gr.TabItem("🔊 发音"):
                gr.Markdown("### 法语音标学习")

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("**选择音标：**")
                        phoneme_buttons  = []
                        phoneme_data_map = {p["symbol"]: p for p in DATA_CACHE["phonemes"]}

                        for p in DATA_CACHE["phonemes"]:
                            btn = gr.Button(
                                p["symbol"], size="sm", elem_classes=["phoneme-btn"]
                            )
                            phoneme_buttons.append((btn, p["symbol"]))

                    with gr.Column(scale=2):
                        phoneme_symbol  = gr.Textbox(label="音标", interactive=False)
                        phoneme_desc    = gr.Textbox(label="发音描述",  interactive=False, lines=3)
                        phoneme_mouth   = gr.Textbox(label="嘴型说明", interactive=False)
                        phoneme_similar = gr.Textbox(label="类比音",   interactive=False, lines=2)
                        audio_player    = gr.Audio(label="发音", type="filepath")
                        audio_status    = gr.Textbox(label="音频状态", interactive=False)

                        phoneme_symbol_state = gr.State("")

                        def show_phoneme(symbol):
                            p = phoneme_data_map.get(symbol, {})
                            audio_path  = None
                            status_msg  = "音频待补全"
                            if p.get("audio_files"):
                                audio_file = p["audio_files"][0]
                                full_path  = ASSETS_DIR / "audio" / "phonemes" / audio_file
                                if full_path.exists():
                                    audio_path = str(full_path)
                                    status_msg = f"播放: {audio_file}"
                                else:
                                    status_msg = f"音频文件缺失: {audio_file}"
                            return (
                                p.get("symbol", ""),
                                (f"中文：{p.get('description_zh', '')}\n"
                                 f"English：{p.get('description_en', '')}"),
                                p.get("mouth_shape_note", ""),
                                (f"中文类比：{p.get('similar_sound_zh', '')}\n"
                                 f"English：{p.get('similar_sound_en', '')}"),
                                audio_path, status_msg,
                            )

                        for btn, symbol in phoneme_buttons:
                            btn.click(
                                lambda s=symbol: s,
                                inputs=[],
                                outputs=[phoneme_symbol_state],
                                api_name=False
                            ).then(
                                show_phoneme,
                                inputs=[phoneme_symbol_state],
                                outputs=[
                                    phoneme_symbol, phoneme_desc, phoneme_mouth,
                                    phoneme_similar, audio_player, audio_status
                                ],
                                api_name=False
                            )

            # =========================================================================
            # Tab 3: 单词与短语
            # =========================================================================
            with gr.TabItem("📚 单词与短语"):
                gr.Markdown("### 背单词 + 间隔重复")

                with gr.Row():
                    with gr.Column(scale=1):
                        vocab_mode      = gr.Radio(
                            choices=[("选择题", "choice"), ("拼写模式", "spelling")],
                            value="choice", label="学习模式"
                        )
                        start_vocab_btn = gr.Button("开始/下一题", variant="primary")
                        gr.Markdown("---")
                        vocab_plan_info = gr.Textbox(
                            label="今日进度", interactive=False, lines=6
                        )

                    with gr.Column(scale=2):
                        vocab_question    = gr.Textbox(label="题目",       interactive=False, lines=2)
                        vocab_options    = gr.Radio(choices=[], label="选项",               visible=False)
                        vocab_input      = gr.Textbox(label="输入法语单词", visible=False)
                        vocab_submit     = gr.Button("提交答案", visible=False)
                        vocab_result     = gr.Textbox(label="结果",  interactive=False)
                        vocab_explanation = gr.Textbox(label="解析", interactive=False, lines=3)
                        vocab_audio       = gr.Audio(label="发音", interactive=False, autoplay=True, visible=False)
                        vocab_audio_btn   = gr.Button("📢 播放发音", visible=False)

                # -----------------------------------------------------------------
                # update_vocab_plan
                # -----------------------------------------------------------------
                def update_vocab_plan(settings, sr, progress):
                    progress    = _cross_day_reset(progress)
                    today_str   = datetime.now().strftime("%Y-%m-%d")
                    lexicon     = DATA_CACHE["lexicon"]

                    if lexicon.empty:
                        return "暂无词汇数据", progress

                    level       = settings["target_level"]
                    level_df    = _filter_level(lexicon, level)
                    total_level = len(level_df)

                    started = sum(
                        1 for wid in level_df["id"].astype(str)
                        if wid in sr
                    )

                    due          = get_due_words(sr, today_str)
                    due_in_level = [
                        wid for wid in due
                        if wid in level_df["id"].astype(str).values
                    ]

                    daily    = settings["daily_new_words"]
                    new_done = progress["new_words_today"]
                    new_left = max(0, daily - new_done)

                    lines = [
                        f"📅 {today_str}",
                        f"✅ 今日新词: {new_done}/{daily}",
                        f"🔄 待复习: {len(due_in_level)} 词",
                        f"📚 本级词汇: {total_level} 词",
                        f"📖 已启动: {started} 词",
                    ]
                    if new_left > 0:
                        lines.append(f"💡 今日还可学新词: {new_left} 个")
                    else:
                        lines.append("🎉 今日新词任务已完成")

                    return "\n".join(lines), progress

                # -----------------------------------------------------------------
                # generate_vocab_question
                # -----------------------------------------------------------------
                def generate_vocab_question(mode, settings, sr_state_val, daily_progress_val):
                    today_str            = datetime.now().strftime("%Y-%m-%d")
                    daily_progress_val   = _cross_day_reset(daily_progress_val)
                    lexicon              = DATA_CACHE["lexicon"]

                    if lexicon.empty:
                        return (
                            "暂无词汇数据",
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            "", "", None,
                            sr_state_val, daily_progress_val, "choice"
                        )

                    level       = settings["target_level"]
                    level_words = _filter_level(lexicon, level)

                    due_ids      = get_due_words(sr_state_val, today_str)
                    due_in_level = [
                        wid for wid in due_ids
                        if wid in level_words["id"].astype(str).values
                    ]

                    if due_in_level:
                        chosen_id  = random.choice(due_in_level)
                        row        = level_words[
                            level_words["id"].astype(str) == chosen_id
                        ].iloc[0]
                        if chosen_id not in sr_state_val:
                            sr_state_val[chosen_id] = {
                                "status": "new", "interval_days": 0,
                                "next_review_date": None,
                                "ease_factor": SR_EASE_DEFAULT, "review_count": 0,
                            }
                        word_id   = chosen_id
                        word_type = "review"
                    else:
                        new_candidates = _get_new_word_candidates(
                            level_words, sr_state_val,
                            settings["daily_new_words"],
                            daily_progress_val["new_words_today"]
                        )
                        if new_candidates:
                            row     = new_candidates[0]
                            word_id = str(row["id"])
                            sr_state_val[word_id] = {
                                "status": "new", "interval_days": 0,
                                "next_review_date": None,
                                "ease_factor": SR_EASE_DEFAULT, "review_count": 0,
                            }
                            daily_progress_val["new_words_today"] += 1
                            word_type = "new"
                        else:
                            return (
                                "🎉 恭喜！今日学习任务已完成\n\n"
                                "✅ 新词目标达成\n"
                                "🔄 暂无待复习词汇\n\n"
                                "明天再来，继续加油！💪",
                                gr.update(visible=False),
                                gr.update(visible=False),
                                gr.update(visible=False),
                                "", "", None,
                                sr_state_val, daily_progress_val, mode
                            )

                    type_tag = "🔄" if word_type == "review" else "🆕"

                    if mode == "choice":
                        correct_meaning = get_meaning_display(
                            row, settings["language_mode"]
                        )
                        distractors     = level_words[
                            level_words["id"].astype(str) != word_id
                        ].sample(min(3, len(level_words) - 1))
                        wrong_meanings  = [
                            get_meaning_display(r, settings["language_mode"])
                            for _, r in distractors.iterrows()
                        ]
                        options         = wrong_meanings + [correct_meaning]
                        random.shuffle(options)

                        question = f"{type_tag}【{row['pos']}】{row['lemma']}"

                        return (
                            question,
                            gr.update(choices=options, visible=True, value=None),
                            gr.update(visible=False),
                            gr.update(visible=True),
                            "", "",
                            word_id,
                            sr_state_val, daily_progress_val, mode,
                            gr.update(visible=False) # vocab_audio_btn
                        )
                    else:
                        meaning  = get_meaning_display(row, settings["language_mode"])
                        question = f"{type_tag} 请拼写：{meaning}"

                        return (
                            question,
                            gr.update(visible=False),
                            gr.update(visible=True, value=""),
                            gr.update(visible=True),
                            "", "",
                            word_id,
                            sr_state_val, daily_progress_val, mode,
                            gr.update(visible=False) # vocab_audio_btn
                        )

                # -----------------------------------------------------------------
                # check_vocab_answer
                # -----------------------------------------------------------------
                def check_vocab_answer(
                    radio_val, text_val, mode,
                    word_id, settings, sr_state_val, daily_progress_val
                ):
                    if word_id is None:
                        return "请先开始题目", "", sr_state_val, daily_progress_val

                    user_answer = radio_val if mode == "choice" else text_val
                    lexicon      = DATA_CACHE["lexicon"]
                    row          = lexicon[lexicon["id"].astype(str) == str(word_id)].iloc[0]

                    if mode == "choice":
                        is_correct = user_answer == get_meaning_display(
                            row, settings["language_mode"]
                        )
                        is_almost_correct = False
                    else:
                        user_clean = (user_answer or "").lower().strip()
                        correct_ans = row["lemma"].lower().strip()
                        if user_clean == correct_ans:
                            is_correct = True
                            is_almost_correct = False
                        elif strip_accents(user_clean) == strip_accents(correct_ans):
                            is_correct = False
                            is_almost_correct = True
                        else:
                            is_correct = False
                            is_almost_correct = False

                    if mode == "choice":
                        quality = 5 if is_correct else 3
                    else:
                        quality = 5 if is_correct else (4 if is_almost_correct else 0)

                    sr_state_val           = update_sr_status(sr_state_val, word_id, quality)
                    daily_progress_val     = _cross_day_reset(daily_progress_val)
                    daily_progress_val["reviewed_today"] += 1

                    if is_correct:
                        result = "✅ 正确！"
                    elif is_almost_correct:
                        result = f"✅ 几乎正确（注意重音符号：正确拼写是 {row['lemma']}）"
                    else:
                        result = f"❌ 错误。正确答案是：{row['lemma']}"
                    
                    explanation = f"例句：{row['example_fr']}\n{row['example_zh']}"

                    return result, explanation, sr_state_val, daily_progress_val, gr.update(visible=True)

                def play_vocab_audio(word_id):
                    if not word_id: return None
                    lexicon = DATA_CACHE["lexicon"]
                    row = lexicon[lexicon["id"].astype(str) == str(word_id)].iloc[0]
                    lemma = row["lemma"]
                    try:
                        tts = gTTS(text=lemma, lang="fr")
                        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="french_crutch_vocab_")
                        tts.save(tmp_file.name)
                        tmp_file.close()
                        return tmp_file.name
                    except:
                        return None

                vocab_mode.change(
                    lambda m: m,
                    inputs=[vocab_mode],
                    outputs=[vocab_mode_state],
                    api_name=False
                )

                start_vocab_btn.click(
                    generate_vocab_question,
                    inputs=[vocab_mode, settings_state, sr_state, daily_progress],
                    outputs=[
                        vocab_question,
                        vocab_options, vocab_input, vocab_submit,
                        vocab_result, vocab_explanation,
                        current_word_id,
                        sr_state, daily_progress,
                        vocab_mode_state,
                        vocab_audio_btn,
                    ]
                )

                vocab_submit.click(
                    check_vocab_answer,
                    inputs=[
                        vocab_options, vocab_input,
                        vocab_mode_state, current_word_id,
                        settings_state, sr_state, daily_progress
                    ],
                    outputs=[vocab_result, vocab_explanation, sr_state, daily_progress, vocab_audio_btn]
                )

                vocab_audio_btn.click(
                    play_vocab_audio,
                    inputs=[current_word_id],
                    outputs=[vocab_audio]
                )

                app.load(
                    update_vocab_plan,
                    inputs=[settings_state, sr_state, daily_progress],
                    outputs=[vocab_plan_info, daily_progress]
                )

            # =========================================================================
            # Tab 4: 听写
            # =========================================================================
            with gr.TabItem("🎧 听写"):
                gr.Markdown("### 听写练习（仅限复习词汇）")

                with gr.Row():
                    with gr.Column(scale=1):
                        dictation_start = gr.Button("开始听写", variant="primary")
                        dictation_replay = gr.Button("🔄 重听", variant="secondary")
                        play_hint = gr.Textbox(
                            label="提示",
                            value="点击开始，然后输入你听到的单词",
                            interactive=False
                        )
                        dictation_stats = gr.Textbox(
                            label="听写统计", interactive=False, lines=3
                        )
                        dictation_audio = gr.Audio(label="听音", interactive=False, autoplay=True, visible=False)

                    with gr.Column(scale=2):
                        dictation_input   = gr.Textbox(label="输入你听到的单词")
                        dictation_submit  = gr.Button("提交")
                        dictation_result  = gr.Textbox(label="结果",     interactive=False)
                        dictation_answer  = gr.Textbox(label="正确答案", interactive=False)

                # -----------------------------------------------------------------
                # start_dictation
                # [修复 3] 成功分支返回额外两个 "" 用于清空 result/answer
                # -----------------------------------------------------------------
                def start_dictation(settings, sr_state_val, daily_progress_val):
                    today_str          = datetime.now().strftime("%Y-%m-%d")
                    daily_progress_val = _cross_day_reset(daily_progress_val)
                    lexicon            = DATA_CACHE["lexicon"]

                    if lexicon.empty:
                        return "暂无词汇", None, "", sr_state_val, daily_progress_val, "", "", "", gr.update(visible=False)

                    level       = settings["target_level"]
                    level_words = _filter_level(lexicon, level)

                    due_ids      = get_due_words(sr_state_val, today_str)
                    due_in_level = [
                        wid for wid in due_ids
                        if wid in level_words["id"].astype(str).values
                    ]

                    if not due_in_level:
                        stats = (
                            f"📅 {today_str}\n"
                            f"🔄 待复习: 0 词\n"
                            f"✅ 请先在「单词」模块开始学习"
                        )
                        return (
                            "📭 今日暂无需要复习听写的单词\n\n"
                            "💡 请先在「单词与短语」模块完成今日学习计划，\n"
                            "    复习词积累后即可开始听写练习。",
                            None, stats,
                            sr_state_val, daily_progress_val,
                            "", "", "",  # ← [修复 3] 清空输入+结果+答案
                            gr.update(visible=False)
                        )

                    chosen_id = random.choice(due_in_level)
                    row       = level_words[
                        level_words["id"].astype(str) == str(chosen_id)
                    ].iloc[0]

                    if str(chosen_id) not in sr_state_val:
                        sr_state_val[str(chosen_id)] = {
                            "status": "new", "interval_days": 0,
                            "next_review_date": None,
                            "ease_factor": SR_EASE_DEFAULT, "review_count": 0,
                        }

                    hint  = f"【{row['pos']}】听发音，输入单词"
                    stats = (
                        f"📅 {today_str}\n"
                        f"🔄 待复习: {len(due_in_level)} 词\n"
                        f"📝 当前: {row['lemma']}"
                    )

                    audio_path = None
                    try:
                        tts = gTTS(text=row["lemma"], lang="fr")
                        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="french_crutch_dictation_")
                        tts.save(tmp_file.name)
                        tmp_file.close()
                        audio_path = tmp_file.name
                    except Exception:
                        pass

                    # ← [修复 3] 成功分支返回额外两个 "" 清空 result/answer
                    return hint, str(chosen_id), stats, sr_state_val, daily_progress_val, "", "", "", gr.update(value=audio_path, visible=True)

                # -----------------------------------------------------------------
                # check_dictation
                # -----------------------------------------------------------------
                def check_dictation(
                    user_input, word_id,
                    settings, sr_state_val, daily_progress_val
                ):
                    if word_id is None:
                        return "请先开始", "", sr_state_val, daily_progress_val

                    lexicon      = DATA_CACHE["lexicon"]
                    row          = lexicon[lexicon["id"].astype(str) == str(word_id)].iloc[0]
                    correct      = row["lemma"].lower().strip()
                    user_clean   = (user_input or "").lower().strip()
                    
                    if user_clean == correct:
                        is_correct = True
                        is_almost_correct = False
                    elif strip_accents(user_clean) == strip_accents(correct):
                        is_correct = False
                        is_almost_correct = True
                    else:
                        is_correct = False
                        is_almost_correct = False

                    quality              = 5 if is_correct else (4 if is_almost_correct else 2)
                    sr_state_val         = update_sr_status(sr_state_val, word_id, quality)
                    daily_progress_val   = _cross_day_reset(daily_progress_val)
                    daily_progress_val["reviewed_today"] += 1

                    if is_correct:
                        result = "✅ 正确！"
                    elif is_almost_correct:
                        result = f"✅ 几乎正确（注意重音符号：正确拼写是 {row['lemma']}）"
                    else:
                        result = "❌ 错误"
                    answer = (f"{row['lemma']} - "
                              f"{get_meaning_display(row, settings['language_mode'])}")

                    return result, answer, sr_state_val, daily_progress_val

                # [修复 3] dictation_start.click：outputs 包含 result 和 answer
                dictation_start.click(
                    start_dictation,
                    inputs=[settings_state, sr_state, daily_progress],
                    outputs=[
                        play_hint, current_word_id, dictation_stats,
                        sr_state, daily_progress,
                        dictation_input,
                        dictation_result,   # ← [修复 3] 新增：清空结果
                        dictation_answer,  # ← [修复 3] 新增：清空答案
                        dictation_audio,
                    ]
                )

                dictation_submit.click(
                    check_dictation,
                    inputs=[
                        dictation_input, current_word_id,
                        settings_state, sr_state, daily_progress
                    ],
                    outputs=[
                        dictation_result, dictation_answer,
                        sr_state, daily_progress
                    ]
                )
                dictation_replay.click(
                    lambda aud: aud,
                    inputs=[dictation_audio],
                    outputs=[dictation_audio],
                    api_name=False
                )

            # =========================================================================
            # Tab 5: 语法
            # =========================================================================
            with gr.TabItem("📝 语法"):
                gr.Markdown("### 语法练习（单选 + 填空）")

                with gr.Row():
                    with gr.Column(scale=1):
                        grammar_start  = gr.Button("下一题", variant="primary")
                        grammar_topic   = gr.Textbox(label="语法点", interactive=False)
                        grammar_level   = gr.Textbox(label="等级",   interactive=False)

                    with gr.Column(scale=2):
                        grammar_question    = gr.Textbox(label="题目",      interactive=False, lines=2)
                        grammar_options     = gr.Radio(choices=[], label="选项",       visible=False)
                        grammar_input       = gr.Textbox(label="填空答案",   visible=False)
                        grammar_submit      = gr.Button("提交",             visible=False)
                        grammar_result      = gr.Textbox(label="结果",       interactive=False)
                        grammar_explanation = gr.Textbox(
                            label="解析", interactive=False, lines=4
                        )

                # -----------------------------------------------------------------
                # generate_grammar_question
                # [修复 2] 所有 return 末尾增加 "" 清空 grammar_explanation
                # -----------------------------------------------------------------
                def generate_grammar_question(settings):
                    questions = DATA_CACHE["grammar"]

                    if not questions:
                        # ← [修复 2] 末尾加 "" 清空解析
                        return (
                            "暂无题目", "", "",
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            None, "", None, ""
                        )

                    level = settings["target_level"]
                    level_qs = (
                        [q for q in questions if q["level"] in [level, "A1", "A2"]]
                        if level == "B1" else questions
                    )
                    if not level_qs:
                        # ← [修复 2] 末尾加 "" 清空解析
                        return (
                            "该等级暂无题目", "", "",
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            None, "", None, ""
                        )

                    q      = random.choice(level_qs)
                    qtype  = q.get("question_type", "single_choice")

                    if qtype == "single_choice":
                        # ← [修复 2] 末尾加 "" 清空解析
                        return (
                            q["grammar_topic"], q["level"], q["question_text"],
                            gr.update(choices=q.get("options", []),
                                      visible=True, value=None),
                            gr.update(visible=False),
                            gr.update(visible=True),
                            q["id"], "", qtype, ""
                        )
                    else:
                        # ← [修复 2] 末尾加 "" 清空解析
                        return (
                            q["grammar_topic"], q["level"], q["question_text"],
                            gr.update(visible=False),
                            gr.update(visible=True, value=""),
                            gr.update(visible=True),
                            q["id"], "", qtype, ""
                        )

                # -----------------------------------------------------------------
                # check_grammar_answer
                # -----------------------------------------------------------------
                def check_grammar_answer(
                    radio_val, text_val, question_id, settings, qtype
                ):
                    if question_id is None:
                        return "请先开始题目", ""

                    questions = DATA_CACHE["grammar"]
                    q = next(
                        (x for x in questions if x["id"] == question_id), None
                    )
                    if q is None:
                        return "题目错误", ""

                    if qtype == "cloze":
                        user_clean = (text_val or "").lower().strip()
                    else:
                        user_clean = (radio_val or "").lower().strip()

                    correct     = q["answer"].lower().strip()
                    is_correct  = user_clean == correct
                    result      = (
                        "✅ 正确！"
                        if is_correct
                        else f"❌ 错误。正确答案是：{q['answer']}"
                    )
                    explanation = get_explanation_display(
                        q.get("explanation_zh", ""),
                        q.get("explanation_en", ""),
                        settings["language_mode"]
                    )

                    return result, explanation

                # [修复 2] grammar_start.click：outputs 加入 grammar_explanation
                grammar_start.click(
                    generate_grammar_question,
                    inputs=[settings_state],
                    outputs=[
                        grammar_topic, grammar_level, grammar_question,
                        grammar_options, grammar_input, grammar_submit,
                        current_grammar_id, grammar_result,
                        current_grammar_qtype,
                        grammar_explanation,  # ← [修复 2] 新增：清空解析
                    ]
                )

                grammar_submit.click(
                    check_grammar_answer,
                    inputs=[
                        grammar_options, grammar_input,
                        current_grammar_id, settings_state,
                        current_grammar_qtype
                    ],
                    outputs=[grammar_result, grammar_explanation]
                )
            # =========================================================================
            # Tab 6: 字母表
            # =========================================================================
            with gr.TabItem("🔤 字母表"):
                gr.Markdown("### 法语 26 个字母发音")

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("**点击字母播放发音：**")
                        alphabet_buttons = []
                        for i in range(26):
                            letter = chr(ord('A') + i)
                            btn = gr.Button(letter, size="sm", elem_classes=["phoneme-btn"])
                            alphabet_buttons.append((btn, letter))

                    with gr.Column(scale=2):
                        alphabet_player = gr.Audio(label="发音", type="filepath", autoplay=True)
                        alphabet_status = gr.Textbox(label="音频状态", interactive=False)

                        def play_alphabet(letter):
                            audio_path = None
                            status_msg = "音频待补全"
                            filename = f"letter_{letter}.mp3"
                            full_path = ASSETS_DIR / "audio" / "alphabet" / filename
                            if full_path.exists():
                                audio_path = str(full_path)
                                status_msg = f"播放: {filename}"
                            else:
                                status_msg = f"音频文件缺失: {filename}"
                            
                            return audio_path, status_msg
                            
                        for btn, letter in alphabet_buttons:
                            btn.click(
                                lambda l=letter: play_alphabet(l),
                                inputs=[],
                                outputs=[alphabet_player, alphabet_status],
                                api_name=False
                            )

        # 页脚
        gr.Markdown("""
        ---
        *法语拐杖 v0.5 | UI polish | 本地开发版*
        """)

    return app

# =============================================================================
# 启动入口
# =============================================================================

app = create_app()

if __name__ == "__main__":
    app.launch()
