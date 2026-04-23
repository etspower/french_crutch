---
title: French Crutch
emoji: 🥖
colorFrom: blue
colorTo: red
sdk: gradio
sdk_version: 4.20.0
app_file: app.py
pinned: false
---

# 🇫🇷 法语拐杖 French Crutch

为法语 0 基础自学者设计的 CEFR B1-B2 学习工具，基于 Gradio 构建。

## 功能模块

| 模块 | 说明 |
|------|------|
| 🔊 **发音** | 法语音标学习，含嘴型说明与类比音提示 |
| 📚 **单词与短语** | 背单词 + 间隔重复（简化版 SM-2） |
| 🎧 **听写** | 听音写词，训练拼写与听力 |
| 📝 **语法** | 单选 + 填空题，覆盖 B1-B2 语法点 |
| ⚙️ **设置** | 语言模式切换（中法+英法 / 纯中法）、目标等级、每日计划 |

## 语言辅助模式

- **模式 A（中法 + 英法）**：解释与提示中同时包含中文和英文
- **模式 B（纯中法）**：所有解释仅用中文，不依赖英文

## 本地运行

### 1. 克隆/下载项目

```bash
cd french_crutch
```

### 2. 创建虚拟环境（推荐）

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行应用

```bash
python app.py
```

应用将在 http://localhost:7860 启动。

## 推送到 Hugging Face Space

### 1. 初始化 Git 仓库

```bash
cd french_crutch
git init
git add .
git commit -m "Initial commit: French Crutch v0.1"
```

### 2. 创建 Hugging Face Space

1. 访问 https://huggingface.co/spaces
2. 点击 "Create new Space"
3. 选择 SDK: **Gradio**
4. 填写 Space 名称（如 `french-crutch`）
5. 选择可见性（Public/Private）

### 3. 配置 Git 凭证

**方式一：使用 Hugging Face CLI（推荐）**

```bash
# 安装 CLI
pip install huggingface-hub

# 登录（会提示输入 Token）
huggingface-cli login
```

**方式二：使用 Git 凭证助手**

```bash
git config --global credential.helper store
# 首次 push 时输入用户名和 Token 作为密码
```

### 4. 推送到 Space

```bash
# 添加远程仓库（替换 <USERNAME> 和 <SPACE_NAME>）
git remote add origin https://huggingface.co/spaces/<USERNAME>/<SPACE_NAME>

# 推送
git push -u origin main
```

推送后，Hugging Face 会自动构建并部署应用。

## 项目结构

```
french_crutch/
├── app.py                          # Gradio 主入口
├── requirements.txt                # Python 依赖
├── README.md                       # 本文件
├── .gitignore                      # Git 忽略规则
├── data/
│   ├── lexicon_sample.csv          # 词典样例（25词）
│   ├── grammar_questions_sample.json  # 语法题库（13题）
│   └── phonemes.json               # 音标数据（8个）
├── assets/
│   ├── audio/phonemes/             # 音标音频（待录制）
│   └── images/mouth_shapes/        # 嘴型图（待补充）
└── tools/
    └── generate_phoneme_audio.py   # 音频生成辅助脚本
```

## 数据扩展说明

### 扩充词典

编辑 `data/lexicon_sample.csv`，添加新行：

```csv
id,lemma,pos,level,zh_meaning,en_meaning,example_fr,example_zh,example_en
26,nouveau,adj,B1,新的,new,C'est une nouvelle idée.,这是个新主意。,This is a new idea.
```

### 扩充语法题

编辑 `data/grammar_questions_sample.json`，添加新题目：

```json
{
  "id": 14,
  "grammar_topic": "Futur simple",
  "level": "B1",
  "question_type": "cloze",
  "question_text": "Demain, je ___ (partir) en vacances.",
  "options": [],
  "answer": "partirai",
  "explanation_zh": "简单将来时：动词不定式 + 词尾。je 词尾 -ai。",
  "explanation_en": "Futur simple: infinitive + ending. je ending -ai."
}
```

### 添加音标音频

1. 录制音频文件（MP3 格式）
2. 保存到 `assets/audio/phonemes/`
3. 更新 `data/phonemes.json` 中的 `audio_files` 字段
4. 或使用辅助脚本：`python tools/generate_phoneme_audio.py`

## 技术说明

### 间隔重复算法

采用简化版 SM-2 算法：
- 答对：间隔按 ease factor 递增
- 答错：重置为最小间隔
- 支持 0-5 质量评分

### 性能优化

- 数据文件在启动时一次性加载，避免运行时 IO 阻塞
- 所有交互函数轻量快速，无长时间 sleep 或循环
- 无自访问/keep-alive 逻辑，遵循 Hugging Face Space 休眠策略

## 许可证

MIT License - 自由使用与修改。

## 致谢

- Gradio: https://gradio.app
- Hugging Face Spaces: https://huggingface.co/spaces
