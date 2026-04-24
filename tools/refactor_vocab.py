import re

def main():
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. UI Replacement
    ui_old = """                        vocab_mode      = gr.Radio(
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
                        vocab_audio_btn   = gr.Button("📢 播放发音", visible=False)"""

    ui_new = """                        vocab_mode      = gr.Radio(
                            choices=[("闪卡复习", "flashcard"), ("拼写模式", "spelling")],
                            value="flashcard", label="学习模式"
                        )
                        start_vocab_btn = gr.Button("开始/下一题", variant="primary")
                        gr.Markdown("---")
                        vocab_plan_info = gr.Textbox(
                            label="今日进度", interactive=False, lines=6
                        )

                    with gr.Column(scale=2):
                        vocab_question    = gr.Markdown("### 请点击左侧开始")
                        vocab_audio       = gr.Audio(label="发音", interactive=False, autoplay=True, visible=False)
                        vocab_audio_btn   = gr.Button("📢 播放发音", visible=False)

                        # Flashcard mode UI
                        vocab_reveal_btn  = gr.Button("👀 显示释义", variant="primary", visible=False)
                        with gr.Group(visible=False) as vocab_card_back:
                            vocab_explanation = gr.Markdown("")
                            with gr.Row():
                                vocab_eval_0 = gr.Button("🔴 不认识", variant="stop")
                                vocab_eval_3 = gr.Button("🟡 模糊", variant="secondary")
                                vocab_eval_4 = gr.Button("🟢 记得", variant="secondary")
                                vocab_eval_5 = gr.Button("🌟 太简单", variant="primary")

                        # Spelling mode UI
                        vocab_input      = gr.Textbox(label="输入法语单词", visible=False)
                        vocab_submit     = gr.Button("提交答案", visible=False)
                        vocab_result     = gr.Textbox(label="结果", interactive=False, visible=False)"""
    
    content = content.replace(ui_old, ui_new)


    # 2. generate_vocab_question replacement
    gen_old = """                def generate_vocab_question(mode, settings, sr_state_val, daily_progress_val):
                    lexicon = DATA_CACHE["lexicon"]
                    level_words = _filter_level(lexicon, settings["target_level"])

                    if level_words.empty:
                        return (
                            "该等级暂无词汇", 
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            "", "", None,
                            sr_state_val, daily_progress_val, mode,
                            gr.update(visible=False)
                        )

                    due_in_level = get_due_words(sr_state_val)
                    due_in_level = [wid for wid in due_in_level if wid in level_words["id"].astype(str).values]

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
                                "### 🎉 恭喜！今日学习任务已完成\\n\\n"
                                "- ✅ 新词目标达成\\n"
                                "- 🔄 暂无待复习词汇\\n\\n"
                                "**明天再来，继续加油！💪**",
                                gr.update(visible=False),
                                gr.update(visible=False),
                                gr.update(visible=False),
                                "", "", None,
                                sr_state_val, daily_progress_val, mode,
                                gr.update(visible=False)
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
                        )"""

    gen_new = """                def generate_vocab_question(mode, settings, sr_state_val, daily_progress_val):
                    lexicon = DATA_CACHE["lexicon"]
                    level_words = _filter_level(lexicon, settings["target_level"])

                    if level_words.empty:
                        return (
                            "该等级暂无词汇", 
                            gr.update(visible=False), gr.update(visible=False),
                            gr.update(visible=False), gr.update(visible=False),
                            gr.update(visible=False), "",
                            None, sr_state_val, daily_progress_val, mode, gr.update(visible=False)
                        )

                    due_in_level = get_due_words(sr_state_val)
                    due_in_level = [wid for wid in due_in_level if wid in level_words["id"].astype(str).values]

                    if due_in_level:
                        chosen_id  = random.choice(due_in_level)
                        row        = level_words[level_words["id"].astype(str) == chosen_id].iloc[0]
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
                                "### 🎉 恭喜！今日学习任务已完成\\n\\n- ✅ 新词目标达成\\n- 🔄 暂无待复习词汇\\n\\n**明天再来，继续加油！💪**",
                                gr.update(visible=False), gr.update(visible=False),
                                gr.update(visible=False), gr.update(visible=False),
                                gr.update(visible=False), "",
                                None, sr_state_val, daily_progress_val, mode, gr.update(visible=False)
                            )

                    type_tag = "🔄" if word_type == "review" else "🆕"

                    if mode == "flashcard":
                        question = f"### {type_tag} 【{row['pos']}】 **{row['lemma']}**"
                        return (
                            question,
                            gr.update(visible=True),  # vocab_reveal_btn
                            gr.update(visible=False), # vocab_card_back
                            gr.update(visible=False), # vocab_input
                            gr.update(visible=False), # vocab_submit
                            gr.update(visible=False), # vocab_result
                            "",                       # vocab_explanation
                            word_id,
                            sr_state_val, daily_progress_val, mode,
                            gr.update(visible=True)   # vocab_audio_btn
                        )
                    else:
                        meaning  = get_meaning_display(row, settings["language_mode"])
                        question = f"### {type_tag} 请拼写：{meaning}"
                        return (
                            question,
                            gr.update(visible=False), # vocab_reveal_btn
                            gr.update(visible=False), # vocab_card_back
                            gr.update(visible=True, value=""), # vocab_input
                            gr.update(visible=True),  # vocab_submit
                            gr.update(visible=True, value=""), # vocab_result
                            "",                       # vocab_explanation
                            word_id,
                            sr_state_val, daily_progress_val, mode,
                            gr.update(visible=False)  # vocab_audio_btn
                        )"""

    content = content.replace(gen_old, gen_new)


    # 3. Add evaluate_vocab_card and reveal_vocab_card
    check_old = """                # -----------------------------------------------------------------
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
                    
                    explanation = f"例句：{row['example_fr']}\\n{row['example_zh']}"

                    return result, explanation, sr_state_val, daily_progress_val, gr.update(visible=True)"""

    check_new = """                # -----------------------------------------------------------------
                # flashcard & spelling handlers
                # -----------------------------------------------------------------
                def reveal_vocab_card(word_id, settings):
                    if not word_id: return gr.update(), gr.update(), gr.update()
                    lexicon = DATA_CACHE["lexicon"]
                    row = lexicon[lexicon["id"].astype(str) == str(word_id)].iloc[0]
                    meaning = get_meaning_display(row, settings["language_mode"])
                    
                    example_zh = row.get('example_zh', '')
                    example_en = row.get('example_en', '')
                    example_trans = example_zh if settings["language_mode"] == "B" else f"{example_zh}\\n> {example_en}"
                    
                    explanation = f"### 💡 {meaning}\\n\\n**📝 例句：**\\n> {row['example_fr']}\\n> {example_trans}"
                    
                    return gr.update(visible=False), gr.update(visible=True), gr.update(value=explanation)
                
                def evaluate_and_next(quality, mode, word_id, settings, sr_state_val, daily_progress_val):
                    if word_id is not None:
                        sr_state_val = update_sr_status(sr_state_val, word_id, quality)
                        daily_progress_val = _cross_day_reset(daily_progress_val)
                        daily_progress_val["reviewed_today"] += 1
                    
                    # Generate the next question directly
                    return generate_vocab_question(mode, settings, sr_state_val, daily_progress_val)

                def check_spelling_answer(
                    text_val, mode, word_id, settings, sr_state_val, daily_progress_val
                ):
                    if word_id is None:
                        return "请先开始题目", "", sr_state_val, daily_progress_val, gr.update()

                    lexicon = DATA_CACHE["lexicon"]
                    row = lexicon[lexicon["id"].astype(str) == str(word_id)].iloc[0]
                    
                    user_clean = (text_val or "").lower().strip()
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

                    quality = 5 if is_correct else (4 if is_almost_correct else 0)

                    sr_state_val = update_sr_status(sr_state_val, word_id, quality)
                    daily_progress_val = _cross_day_reset(daily_progress_val)
                    daily_progress_val["reviewed_today"] += 1

                    if is_correct:
                        result = "✅ 正确！"
                    elif is_almost_correct:
                        result = f"✅ 几乎正确（注意重音符号：正确拼写是 {row['lemma']}）"
                    else:
                        result = f"❌ 错误。正确答案是：{row['lemma']}"
                    
                    meaning = get_meaning_display(row, settings["language_mode"])
                    example_zh = row.get('example_zh', '')
                    example_en = row.get('example_en', '')
                    example_trans = example_zh if settings["language_mode"] == "B" else f"{example_zh}\\n> {example_en}"
                    
                    explanation = f"### 💡 {row['lemma']} - {meaning}\\n\\n**📝 例句：**\\n> {row['example_fr']}\\n> {example_trans}"

                    return result, explanation, sr_state_val, daily_progress_val, gr.update(visible=True)"""

    content = content.replace(check_old, check_new)


    # 4. Event handlers
    events_old = """                start_vocab_btn.click(
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
                , api_name=False)

                vocab_submit.click(
                    check_vocab_answer,
                    inputs=[
                        vocab_options, vocab_input,
                        vocab_mode_state, current_word_id,
                        settings_state, sr_state, daily_progress
                    ],
                    outputs=[vocab_result, vocab_explanation, sr_state, daily_progress, vocab_audio_btn]
                , api_name=False)"""

    events_new = """                # UI Outputs format:
                # [vocab_question, vocab_reveal_btn, vocab_card_back, vocab_input, vocab_submit, vocab_result, vocab_explanation, current_word_id, sr_state, daily_progress, vocab_mode_state, vocab_audio_btn]
                
                start_vocab_btn.click(
                    generate_vocab_question,
                    inputs=[vocab_mode, settings_state, sr_state, daily_progress],
                    outputs=[
                        vocab_question,
                        vocab_reveal_btn, vocab_card_back, vocab_input, vocab_submit, vocab_result,
                        vocab_explanation,
                        current_word_id,
                        sr_state, daily_progress,
                        vocab_mode_state,
                        vocab_audio_btn,
                    ]
                , api_name=False)

                vocab_reveal_btn.click(
                    reveal_vocab_card,
                    inputs=[current_word_id, settings_state],
                    outputs=[vocab_reveal_btn, vocab_card_back, vocab_explanation],
                    api_name=False
                )

                # Flashcard evaluations
                for btn, qual in [(vocab_eval_0, 0), (vocab_eval_3, 3), (vocab_eval_4, 4), (vocab_eval_5, 5)]:
                    btn.click(
                        lambda m, wid, st, sr, dp, q=qual: evaluate_and_next(q, m, wid, st, sr, dp),
                        inputs=[vocab_mode_state, current_word_id, settings_state, sr_state, daily_progress],
                        outputs=[
                            vocab_question,
                            vocab_reveal_btn, vocab_card_back, vocab_input, vocab_submit, vocab_result,
                            vocab_explanation,
                            current_word_id,
                            sr_state, daily_progress,
                            vocab_mode_state,
                            vocab_audio_btn,
                        ],
                        api_name=False
                    )

                vocab_submit.click(
                    check_spelling_answer,
                    inputs=[
                        vocab_input,
                        vocab_mode_state, current_word_id,
                        settings_state, sr_state, daily_progress
                    ],
                    outputs=[vocab_result, vocab_explanation, sr_state, daily_progress, vocab_audio_btn]
                , api_name=False)"""

    content = content.replace(events_old, events_new)

    with open("app.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    main()
