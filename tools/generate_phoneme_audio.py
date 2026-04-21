#!/usr/bin/env python3
"""
generate_phoneme_audio.py
用于辅助批量生成音标音频文件的占位脚本

功能：
1. 读取 data/phonemes.json
2. 检查每个音标的 audio_files 字段
3. 如果为空，输出建议文件名供人工录制

使用方法：
    python tools/generate_phoneme_audio.py

输出示例：
    [待录制] /a/ -> assets/audio/phonemes/a_open_1.mp3
    [已存在] /e/ -> assets/audio/phonemes/e_close_mid_1.mp3
"""

import json
import os
from pathlib import Path

# 路径配置
PROJECT_ROOT = Path(__file__).parent.parent
PHONEMES_PATH = PROJECT_ROOT / "data" / "phonemes.json"
AUDIO_DIR = PROJECT_ROOT / "assets" / "audio" / "phonemes"


def load_phonemes():
    """加载音标数据"""
    if not PHONEMES_PATH.exists():
        print(f"错误：找不到文件 {PHONEMES_PATH}")
        return []
    
    with open(PHONEMES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_audio_files(phonemes):
    """检查音频文件状态"""
    # 确保音频目录存在
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("法语音标音频文件检查报告")
    print("=" * 60)
    print()
    
    to_record = []
    existing = []
    
    for p in phonemes:
        symbol = p.get("symbol", "未知")
        phoneme_id = p.get("phoneme_id", "")
        audio_files = p.get("audio_files", [])
        
        if not audio_files:
            # 生成建议文件名
            # 从 symbol 中提取字母，如 /a/ -> a_open_1.mp3
            clean_symbol = symbol.strip("/\\")
            suggested_name = f"{clean_symbol}_1.mp3"
            to_record.append({
                "symbol": symbol,
                "phoneme_id": phoneme_id,
                "suggested_file": suggested_name,
                "description_zh": p.get("description_zh", "")[:50]
            })
        else:
            # 检查文件是否实际存在
            for af in audio_files:
                file_path = AUDIO_DIR / af
                if file_path.exists():
                    existing.append({
                        "symbol": symbol,
                        "file": af,
                        "path": str(file_path)
                    })
                else:
                    to_record.append({
                        "symbol": symbol,
                        "phoneme_id": phoneme_id,
                        "suggested_file": af,
                        "description_zh": p.get("description_zh", "")[:50],
                        "note": "文件已配置但缺失"
                    })
    
    # 输出待录制列表
    if to_record:
        print(f"【待录制/缺失】共 {len(to_record)} 个音标：")
        print("-" * 60)
        for item in to_record:
            note = f" ({item.get('note', '')})" if item.get('note') else ""
            print(f"  音标: {item['symbol']}{note}")
            print(f"  建议文件名: {item['suggested_file']}")
            print(f"  发音提示: {item['description_zh']}...")
            print(f"  完整路径: assets/audio/phonemes/{item['suggested_file']}")
            print()
    
    # 输出已存在列表
    if existing:
        print(f"【已存在】共 {len(existing)} 个音频文件：")
        print("-" * 60)
        for item in existing:
            print(f"  音标: {item['symbol']} -> {item['file']}")
        print()
    
    # 输出录制指南
    print("=" * 60)
    print("录制指南")
    print("=" * 60)
    print("""
1. 使用录音设备（手机/电脑/专业麦克风）录制每个音标
2. 每个音标录制 1-2 秒清晰发音
3. 导出为 MP3 格式，采样率 44100Hz，单声道
4. 按上方建议的文件名保存到：assets/audio/phonemes/
5. 更新 data/phonemes.json 中的 audio_files 字段

提示：
- 保持录音环境安静，避免回声
- 每个音标重复录制 2-3 遍，选择最清晰的一版
- 可以在文件名后加 _1, _2 区分不同变体
""")
    
    return to_record, existing


def generate_recording_script(phonemes):
    """生成录制脚本文本（供打印使用）"""
    output_path = PROJECT_ROOT / "tools" / "recording_checklist.txt"
    
    lines = ["法语拐杖 - 音标录制清单", "=" * 50, ""]
    
    for p in phonemes:
        symbol = p.get("symbol", "")
        desc = p.get("description_zh", "")[:40]
        audio_files = p.get("audio_files", [])
        
        status = "[ ] 待录制"
        if audio_files:
            status = "[✓] 已配置"
        
        lines.append(f"{status} {symbol} - {desc}")
    
    lines.extend(["", "=" * 50, "录制完成后勾选方框"])
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"录制清单已保存到: {output_path}")


def main():
    """主函数"""
    print("法语拐杖 - 音标音频生成助手")
    print()
    
    phonemes = load_phonemes()
    if not phonemes:
        return
    
    print(f"已加载 {len(phonemes)} 个音标定义")
    print()
    
    to_record, existing = check_audio_files(phonemes)
    
    # 生成录制清单
    generate_recording_script(phonemes)
    
    print()
    print(f"总结: {len(existing)} 个文件已就绪, {len(to_record)} 个待录制")
    print("运行完成。请按上方指南录制音频文件。")


if __name__ == "__main__":
    main()