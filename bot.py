import os
import json
import time
import random
import requests
import traceback
import sys
import re
import glob
import urllib3
from datetime import datetime
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, TextClip, CompositeVideoClip, ColorClip
from moviepy.video.fx.all import crop, resize

# إخفاء تحذيرات الأمان
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === استدعاءات إنستجرام ===
try:
    from instagrapi import Client
except ImportError:
    raise Exception("❌ مكتبة instagrapi غير مثبتة.")

import arabic_reshaper
from bidi.algorithm import get_display

# ================= الإعدادات والمفاتيح =================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
ERROR_BOT_TOKEN = os.environ.get("ERROR_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HISTORY_FILE = "history.json"
SESSION_FILE = "session.json"

# ================= نظام إشعارات تليجرام =================
def send_telegram_alert(message):
    if not ERROR_BOT_TOKEN or not ADMIN_CHAT_ID: return
    url = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, data=payload)
    except: pass

# ================= دالة مفتش الجودة =================
def is_valid_audio(filepath):
    try:
        if not os.path.exists(filepath): return False
        if os.path.getsize(filepath) < 50000: return False 
        clip = AudioFileClip(filepath)
        dur = clip.duration
        clip.close()
        return dur > 0
    except:
        return False

# ================= ✂️ المقص الذكي =================
def crop_to_vertical(clip):
    target_ratio = 9 / 16
    clip_ratio = clip.w / clip.h
    if clip_ratio > target_ratio: 
        new_w = int(clip.h * target_ratio)
        x_center = clip.w / 2
        cropped_clip = crop(clip, width=new_w, height=clip.h, x_center=x_center)
    else: 
        new_h = int(clip.w / target_ratio)
        y_center = clip.h / 2
        cropped_clip = crop(clip, width=clip.w, height=new_h, y_center=y_center)
    return resize(cropped_clip, height=1920, width=1080)

# ================= 🧠 القص الذكي (عبر Gemini) =================
def get_smart_timestamps(transcript_segments):
    if not GEMINI_API_KEY: return None, None, "مفتاح مفقود."
    full_text_with_time = "".join([f"[{seg.start:.2f}s - {seg.end:.2f}s]: {seg.text}\n" for seg in transcript_segments])

    prompt = f"""
    أنت خبير في القرآن. أمامك نص مستخرج من تلاوة.
    حدد البداية والنهاية (بالثواني) لعمل مقطع بين 40 و 58 ثانية:
    1. البداية: ابدأ مع أول كلمة فعلية للتلاوة.
    2. النهاية: يجب أن تكون عند نهاية آية تامة المعنى لتجنب القص العشوائي.
    
    النص:
    {full_text_with_time}
    
    أجب فقط بهذه الصيغة الرياضية:
    START: 00.00
    END: 00.00
    """
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}}
        response = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
        
        if response.status_code == 200:
            text_response = response.json()['candidates'][0]['content']['parts'][0]['text']
            match_start = re.search(r'START:\s*([0-9.]+)', text_response)
            match_end = re.search(r'END:\s*([0-9.]+)', text_response)
            if match_start and match_end:
                return float(match_start.group(1)), float(match_end.group(1)), None
        return None, None, f"خطأ الاتصال: {response.status_code}"
    except Exception as e: return None, None, str(e)

# ================= إصلاح النص العربي =================
def fix_arabic(text):
    if not text: return ""
    reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})
    return get_display(reshaper.reshape(f" {text} "))

# ================= 🏛️ المحرك الأساسي (MP3Quran) والاحتياطي (SoundCloud) =================

MP3QURAN_RECITERS = [
    {"path": "a_mosaad", "name": "عبدالرحمن مسعد"},
    {"path": "yasser_d", "name": "ياسر الدوسري"} # yasser_d هو مساره الرسمي في سيرفر 11
]

SOUNDCLOUD_QUERIES = [
    "عبدالله شعبان تلاوة",
    "عبدالله شعبان قرآن",
    "عبدالله شعبان سورة"
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f: return json.load(f)
        except: pass
    return {"used_pexels": [], "used_surahs": []}

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

# ================= 🔍 الرادار الذكي (للبحث عن السور المتوفرة) =================
def hunt_mp3quran_url():
    print("📡 جاري البحث في سيرفرات MP3Quran عن سورة متوفرة...")
    # نعطيه 30 محاولة ليجد سورة صالحة (لأن عبد الرحمن مسعد لا يملك 114 سورة كاملة)
    for _ in range(30):
        reciter = random.choice(MP3QURAN_RECITERS)
        surah_num = random.randint(1, 114)
        url = f"https://server11.mp3quran.net/{reciter['path']}/{surah_num:03d}.mp3"
        
        try:
            # نستخدم HEAD لسرعة الفحص (أجزاء من الثانية) بدلاً من تحميل الملف
            r = requests.head(url, timeout=5, verify=False)
            if r.status_code == 200:
                print(f"✅ تم العثور على سورة رقم {surah_num:03d} للقارئ {reciter['name']}")
                return url, reciter['name'], f"سورة رقم {surah_num}"
        except: pass
    return None, None, None

def download_file(url, ext="mp3"):
    fname = f"raw_audio_{random.randint(100,999)}.{ext}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=60, stream=True, verify=False)
        if r.status_code in [200, 206]:
            with open(fname, "wb") as f:
                for chunk in r.iter_content(8192): f.write(chunk)
            if is_valid_audio(fname): return fname
    except: pass
    return None

# ================= بروتوكول التشغيل الرئيسي =================
def fetch_and_trim_audio():
    for f in glob.glob("raw_audio*") + ["temp_analysis.mp3", "final_audio.mp3"]:
        try: os.remove(f)
        except: pass

    downloaded_file = None
    reciter_name = ""
    video_title = ""

    # 1️⃣ الخطة الأساسية المنيعة (MP3Quran) - احتمال 85% للتشغيل
    # جعلنا 15% فرصة لتشغيل SoundCloud لكي لا يُنسى عبد الله شعبان تماماً
    if random.random() < 0.85:
        print("1️⃣ المحرك الأساسي (MP3Quran) قيد العمل...")
        mp3_url, reciter_name, video_title = hunt_mp3quran_url()
        if mp3_url:
            print("🔗 جاري تحميل المقطع من السيرفر المباشر...")
            downloaded_file = download_file(mp3_url)

    # 2️⃣ المحرك الاحتياطي (SoundCloud) - لعبدالله شعبان أو إذا فشل الأساسي
    if not downloaded_file:
        print("2️⃣ المحرك الاحتياطي (SoundCloud) قيد العمل لعبدالله شعبان...")
        search_query = random.choice(SOUNDCLOUD_QUERIES)
        ydl_opts = {
            'format': 'bestaudio/best', 
            'outtmpl': 'raw_audio_sc.%(ext)s', 
            'quiet': True,
            'default_search': 'scsearch5', # يبحث في ساوند كلاود
            'nocheckcertificate': True
        }
        try:
            with YoutubeDL(ydl_opts) as ydl_dl:
                ydl_dl.download([search_query])
            files = glob.glob("raw_audio_sc.*")
            if files and is_valid_audio(files[0]):
                downloaded_file = files[0]
                reciter_name = "عبدالله شعبان"
                video_title = "تلاوة عذبة"
                print("✅ تم السحب من SoundCloud بنجاح!")
        except Exception as e:
            print(f"❌ فشل SoundCloud: {e}")

    if not downloaded_file:
        raise Exception("🚨 فشل المحرك الأساسي والاحتياطي معاً (تأكد من اتصال السيرفر).")

    print("🧠 جاري تحليل الصوت وإجراء القص الذكي (Time-Jumping)...")
    full_audio = AudioFileClip(downloaded_file)
    
    # 🌟 ميزة القفز الزمني (Time-Jumping) 🌟
    # بما أن سور القرآن طويلة، نختار 3 دقائق عشوائية من منتصف السورة لنحللها
    max_start = max(0, full_audio.duration - 180.0) 
    start_time_for_clip = random.uniform(0.0, max_start)
    
    analysis_subclip = full_audio.subclip(start_time_for_clip, min(start_time_for_clip + 150.0, full_audio.duration))
    analysis_subclip.write_audiofile("temp_analysis.mp3", logger=None)
    
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe("temp_analysis.mp3", beam_size=5, word_timestamps=True)
    segments_list = list(segments)
    try: os.remove("temp_analysis.mp3")
    except: pass

    rel_start, rel_end, _ = get_smart_timestamps(segments_list)
    
    if rel_start is None or rel_end is None:
        rel_start = 0.0
        if start_time_for_clip == 0.0:
            for s in segments_list:
                if any(w in s.text for w in ["بسم", "أعوذ", "الحمد"]):
                    rel_start = s.start; break
        rel_end = min(rel_start + 55.0, analysis_subclip.duration)
        best_gap = 0
        for i in range(len(segments_list) - 1):
            if segments_list[i].end > (rel_start + 45.0):
                gap = segments_list[i+1].start - segments_list[i].end
                if gap > 1.2 and gap > best_gap: 
                    best_gap = gap; rel_end = segments_list[i].end + (gap/2); break

    absolute_start = start_time_for_clip + rel_start
    absolute_end = start_time_for_clip + rel_end

    final_audio_duration = absolute_end - absolute_start
    trimmed_audio = full_audio.subclip(absolute_start, absolute_end)
    final_audio = trimmed_audio.audio_fadein(1.0).audio_fadeout(2.5) 
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    
    final_audio.close(); full_audio.close()
    try: os.remove(downloaded_file)
    except: pass
    
    return final_audio_duration, video_title, reciter_name

# ================= 3. جلب فيديوهات الطبيعة =================
def fetch_pexels_videos(target_duration, history):
    today = datetime.now().strftime("%A")
    query = "drone landscape, nature" if today in ['Sunday', 'Tuesday', 'Thursday'] else "clouds, peaceful nature"
    res_data = requests.get(f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&size=large&per_page=30&page={random.randint(1, 3)}", headers={"Authorization": PEXELS_API_KEY}).json()
    
    video_files, current_duration = [], 0
    for video in res_data['videos']:
        vid_id_str = str(video['id'])
        if vid_id_str in history['used_pexels'] or any(t in str(video['tags']).lower() for t in ['people', 'woman', 'face']): continue
        
        vid_data = requests.get(video['video_files'][0]['link']).content
        vid_name = f"bg_{vid_id_str}.mp4"
        with open(vid_name, "wb") as f: f.write(vid_data)
        
        clip = VideoFileClip(vid_name)
        vertical_clip = crop_to_vertical(clip)
        
        video_files.append((vertical_clip, vid_name))
        current_duration += vertical_clip.duration
        history['used_pexels'].append(vid_id_str)
        if len(history['used_pexels']) > 60: history['used_pexels'].pop(0)
        if current_duration >= target_duration: break
    return video_files, history

# ================= 4. المونتاج =================
def render_cinematic_video(audio_duration, clips_data):
    clips = [data[0] for data in clips_data]
    final_video = concatenate_videoclips(clips, method="compose").subclip(0, audio_duration)
    dark_overlay = ColorClip(size=(1080, 1920), color=(0,0,0)).set_opacity(0.3).set_duration(audio_duration)
    
    txt_main = TextClip(fix_arabic("عافية قلب"), font="taj.ttf", fontsize=45, color='white', stroke_color='black', stroke_width=2, method='caption', size=(900, None), align='center')
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1.0)
    
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main], size=(1080, 1920))
    video_with_audio = video_with_audio.fadein(1.0).fadeout(1.5)
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    video_with_audio.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac", threads=4)
    
    video_with_audio.close(); final_video.close(); dark_overlay.close()
    for clip, name in clips_data:
        try: clip.close(); os.remove(name)
        except: pass

# ================= 5. صمام النشر لإنستجرام =================
def publish_to_instagram(reciter_name, title):
    try:
        url_tg = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendVideo"
        with open('final_reel.mp4', 'rb') as video_file:
            requests.post(url_tg, data={'chat_id': ADMIN_CHAT_ID, 'caption': f"🎥 مقطع جاهز!\n\nالقارئ: {reciter_name}\nالعنوان: {title}"}, files={'video': video_file}, timeout=200)
    except: pass

    is_thursday = datetime.now().strftime("%A") == "Thursday"
    if is_thursday:
        caption = f"✨ نور ما بين الجمعتين. لا تنسوا السنن والصلاة على النبي ﷺ.\n\nتلاوة القارئ: {reciter_name} 🤍\n#يوم_الجمعة #قرآن #عافية_قلب #تلاوة #راحة_نفسية"
    else:
        caption = f"عافية لقلبك 🤍. أرح مسمعك بتلاوة القارئ {reciter_name}.\n\n#قرآن #تلاوة #عافية_قلب #راحة #طمأنينة"
    
    cl = Client()
    if os.path.exists(SESSION_FILE): cl.load_settings(SESSION_FILE)
    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(SESSION_FILE)
        cl.clip_upload("final_reel.mp4", caption)
        print("🎉 تم النشر بنجاح!")
    except Exception as e:
        raise Exception(f"❌ فشل النشر: {str(e)}")

# ================= التشغيل الرئيسي =================
if __name__ == "__main__":
    history = load_history()
    max_retries = 3 
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n🚀 محاولة {attempt}/{max_retries}...")
            dur, title, reciter = fetch_and_trim_audio()
            clips_data, history = fetch_pexels_videos(dur, history)
            render_cinematic_video(dur, clips_data)
            publish_to_instagram(reciter, title)
            save_history(history)
            send_telegram_alert("✅ تم النشر بنجاح وبتوفيق الله!")
            break 
        except Exception as e:
            if attempt < max_retries:
                send_telegram_alert(f"⚠️ فشل محاولة {attempt}. جاري إعادة المحاولة...\nالسبب: `{str(e)}`")
                time.sleep(10)
            else:
                send_telegram_alert(f"🚨 فشل نهائي بعد 3 محاولات!\nالسبب: `{str(e)}`")
                sys.exit(1)
