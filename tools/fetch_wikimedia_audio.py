import os
import requests
import time
import sys
from pathlib import Path
from pydub import AudioSegment
from gtts import gTTS

# 强制输出为 UTF-8 避免 Windows 控制台编码问题
sys.stdout.reconfigure(encoding='utf-8')

# 常量
USER_AGENT = "FrenchCrutchBot/1.0 (https://github.com/FrenchCrutch)"
HEADERS = {"User-Agent": USER_AGENT}

BASE_DIR = Path(__file__).parent.parent
ASSETS_DIR = BASE_DIR / "assets" / "audio"
PHONEMES_DIR = ASSETS_DIR / "phonemes"
ALPHABET_DIR = ASSETS_DIR / "alphabet"
LOG_FILE = BASE_DIR / "missing_audio.log"

PHONEMES_DIR.mkdir(parents=True, exist_ok=True)
ALPHABET_DIR.mkdir(parents=True, exist_ok=True)

# 扩展映射表：增加 IPA 描述性文件名作为备选
IPA_DESC_MAP = {
    "a": "Open front unrounded vowel.ogg",
    "ɑ": "Open back unrounded vowel.ogg",
    "e": "Close-mid front unrounded vowel.ogg",
    "ɛ": "Open-mid front unrounded vowel.ogg",
    "i": "Close front unrounded vowel.ogg",
    "o": "Close-mid back rounded vowel.ogg",
    "ɔ": "Open-mid back rounded vowel.ogg",
    "u": "Close back rounded vowel.ogg",
    "y": "Close front rounded vowel.ogg",
    "ø": "Close-mid front rounded vowel.ogg",
    "œ": "Open-mid front rounded vowel.ogg",
    "ə": "Mid central vowel.ogg",
    "ɑ̃": "Nasal open back unrounded vowel.ogg",
    "ɛ̃": "Nasal open-mid front unrounded vowel.ogg",
    "ɔ̃": "Nasal open-mid back rounded vowel.ogg",
    "œ̃": "Nasal open-mid front rounded vowel.ogg",
}

PHONEMES_MAP = {
    "a": "01_a_open.mp3", "ɑ": "02_ɑ_open_back.mp3", "e": "03_e_close-mid_front.mp3",
    "ɛ": "04_ɛ_open-mid_front.mp3", "i": "05_i_close_front.mp3", "o": "06_o_close-mid_back.mp3",
    "ɔ": "07_ɔ_open-mid_back.mp3", "u": "08_u_close_back.mp3", "y": "09_y_close_front_rounded.mp3",
    "ø": "10_ø_close-mid_front_rounded.mp3", "œ": "11_œ_open-mid_front_rounded.mp3",
    "ə": "12_ə_schwa.mp3", "ɑ̃": "13_ɑ̃_nasal.mp3", "ɛ̃": "14_ɛ̃_nasal.mp3",
    "ɔ̃": "15_ɔ̃_nasal.mp3", "œ̃": "16_œ̃_nasal.mp3", "j": "17_j_yod.mp3",
    "w": "18_w_wau.mp3", "ɥ": "19_ɥ_u-yod.mp3", "p": "20_p_voiceless.mp3",
    "t": "21_t_voiceless.mp3", "k": "22_k_voiceless.mp3", "b": "23_b_voiced.mp3",
    "d": "24_d_voiced.mp3", "ɡ": "25_ɡ_voiced.mp3", "f": "26_f_voiceless.mp3",
    "s": "27_s_voiceless.mp3", "ʃ": "28_ʃ_voiceless.mp3", "v": "29_v_voiced.mp3",
    "z": "30_z_voiced.mp3", "ʒ": "31_ʒ_voiced.mp3", "m": "32_m_nasal.mp3",
    "n": "33_n_nasal.mp3", "ɲ": "34_ɲ_palatal_nasal.mp3", "ŋ": "35_ŋ_velar_nasal.mp3",
    "l": "36_l_lateral.mp3", "ʁ": "37_ʁ_uvular.mp3", "h": "38_h_aspirate.mp3"
}

def search_wikimedia(query):
    url = "https://commons.wikimedia.org/w/api.php"
    params = {"action": "query", "list": "search", "srnamespace": 6, "srsearch": query, "format": "json", "srlimit": 1}
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        search_results = r.json().get("query", {}).get("search", [])
        if search_results: return search_results[0]["title"]
    except: pass
    return None

def download_file(filename, output_path):
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename.replace('File:', '')}"
    try:
        r = requests.get(url, headers=HEADERS, allow_redirects=False, timeout=15)
        if 300 <= r.status_code < 400:
            url = r.headers['Location']
            r = requests.get(url, headers=HEADERS, stream=True, timeout=15)
        else:
            r = requests.get(url, headers=HEADERS, stream=True, timeout=15)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except: return False

def generate_gtts_fallback(text, output_path):
    """使用 Google TTS 作为最终保底"""
    try:
        tts = gTTS(text=text, lang='fr')
        tts.save(output_path)
        return True
    except Exception as e:
        print(f"  [gTTS Error] {e}")
        return False

def process_item(symbol, target_filename, is_alphabet=False):
    target_path = (ALPHABET_DIR if is_alphabet else PHONEMES_DIR) / target_filename
    if target_path.exists(): return True

    # 1. 尝试 Wikimedia
    wiki_file = None
    queries = [
        f'intitle:"Fr-{symbol}.ogg"',
        f'intitle:"French pronunciation {symbol}.ogg"',
    ]
    if not is_alphabet and symbol in IPA_DESC_MAP:
        queries.append(f'intitle:"{IPA_DESC_MAP[symbol]}"')

    for q in queries:
        wiki_file = search_wikimedia(q)
        if wiki_file: break
    
    if not wiki_file:
        wiki_file = f"File:Fr-{symbol}.ogg" # 最后的猜测

    temp_ogg = target_path.with_suffix('.ogg')
    if download_file(wiki_file, temp_ogg):
        try:
            AudioSegment.from_file(temp_ogg).export(target_path, format="mp3", bitrate="128k")
            print(f"  [Wiki] {symbol} -> {target_filename}")
            temp_ogg.unlink(missing_ok=True)
            return True
        except: pass
    
    # 2. 尝试 gTTS 保底
    if generate_gtts_fallback(symbol, target_path):
        print(f"  [gTTS] {symbol} -> {target_filename} (Fallback)")
        return True

    return False

def main():
    print("=== 开始补全音频 ===")
    missing = []
    for symbol, filename in PHONEMES_MAP.items():
        if not process_item(symbol, filename):
            missing.append(f"Phoneme: {symbol}")
    
    for i in range(26):
        letter = chr(ord('A') + i)
        if not process_item(letter, f"letter_{letter}.mp3", is_alphabet=True):
            missing.append(f"Alphabet: {letter}")

    if missing:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(missing))
    print("=== 处理完成 ===")

if __name__ == "__main__":
    main()
