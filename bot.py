import os
import json
import time
import random
import requests
import traceback
import sys
from datetime import datetime
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, TextClip, CompositeVideoClip, ColorClip
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired # استيراد خطأ التأكيد

# ================= الإعدادات والمفاتيح =================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
ERROR_BOT_TOKEN = os.environ.get("ERROR_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES")
HISTORY_FILE = "history.json"
SESSION_FILE = "session.json"

# ================= 0. نظام إشعارات تليجرام =================
def send_telegram_alert(message):
    if not ERROR_BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload)
    except Exception:
        pass

# ================= 1. نظام الذاكرة =================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                if "used_videos" not in data:
                    data["used_videos"] = []
                return data
        except:
            return {"used_videos": []}
    return {"used_videos": []}

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

def setup_cookies():
    if YOUTUBE_COOKIES and len(YOUTUBE_COOKIES) > 10:
        with open("cookies.txt", "w") as f:
            f.write(YOUTUBE_COOKIES)
        return "cookies.txt"
    return None

# ================= 2. تحميل الصوت =================
def fetch_and_trim_audio():
    history = load_history()
    cookie_file = setup_cookies()
    
    ydl_opts_flat = {'quiet': True, 'extract_flat': True}
    if cookie_file: ydl_opts_flat['cookiefile'] = cookie_file
    
    CHANNELS = [
        {"url": "https://www.youtube.com/@abdullahshaab1/videos", "name": "عبدالله شعبان"},
        {"url": "https://www.youtube.com/@9li9/videos", "name": "عبدالرحمن مسعد"}
    ]
    
    forbidden_keywords = ['أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 'رقية', 'رقيّه']
    selected_video = None
    selected_reciter = ""
    random.shuffle(CHANNELS)
    
    with YoutubeDL(ydl_opts_flat) as ydl:
        for channel in CHANNELS:
            print(f"جاري البحث في قناة: {channel['name']}...")
            try:
                info = ydl.extract_info(channel['url'], download=False)
                for entry in info.get('entries', []):
                    vid_id = entry.get('id', '')
                    title = entry.get('title', '')
                    is_forbidden = any(word in title for word in forbidden_keywords)
                    if len(vid_id) == 11 and vid_id not in history['used_videos'] and not is_forbidden:
                        selected_video = entry
                        selected_reciter = channel['name']
                        break
                if selected_video: break
            except: continue
                
    if not selected_video: raise Exception("لم أجد فيديوهات جديدة!")

    vid_id = selected_video['id']
    video_title = selected_video['title']
    video_url = f"https://www.youtube.com/watch?v={vid_id}"
    
    ydl_opts_dl = {
        'format': 'ba/b/18', 'outtmpl': 'raw_audio.%(ext)s',
        'quiet': True, 'impersonate': 'chrome', 
        'extractor_args': {'youtube': ['player_client=android']},
    }
    if cookie_file: ydl_opts_dl['cookiefile'] = cookie_file
    with YoutubeDL(ydl_opts_dl) as ydl_dl: ydl_dl.download([video_url])

    full_audio = AudioFileClip("raw_audio.mp3") 
    short_audio_duration = min(60.0, full_audio.duration)
    short_audio = full_audio.subclip(0, short_audio_duration)
    short_audio.write_audiofile("short_audio.mp3", logger=None)
    full_audio.close()

    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe("short_audio.mp3", beam_size=5)
    
    end_time = 50.0 
    prev_end = 0
    for segment in segments:
        if segment.end > 40 and (segment.start - prev_end) > 1.2:
            end_time = prev_end
            break
        prev_end = segment.end
    
    final_audio = AudioFileClip("short_audio.mp3").subclip(0, end_time).audio_fadeout(2)
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    final_audio.close()
    return end_time, video_title, vid_id, selected_reciter

# ================= 3. جلب فيديوهات الطبيعة =================
def fetch_pexels_videos(target_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query=nature&orientation=portrait&size=large&per_page=10"
    res_data = requests.get(url, headers=headers).json()
    video_files = []
    current_duration = 0
    for i, video in enumerate(res_data['videos']):
        link = video['video_files'][0]['link']
        vid_data = requests.get(link).content
        with open(f"bg_vid_{i}.mp4", "wb") as f: f.write(vid_data)
        clip = VideoFileClip(f"bg_vid_{i}.mp4")
        video_files.append(clip)
        current_duration += clip.duration
        if current_duration >= target_duration: break
    return video_files

# ================= 4. المونتاج =================
def render_cinematic_video(audio_duration, reciter_name):
    clips = fetch_pexels_videos(audio_duration)
    final_video = concatenate_videoclips(clips, method="compose", padding=-1).subclip(0, audio_duration)
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    txt_main = TextClip("عافية قلب", font="taj.ttf", fontsize=80, color='white').set_position('center').set_duration(audio_duration)
    txt_sub = TextClip(f"القارئ: {reciter_name}", font="taj.ttf", fontsize=40, color='white').set_position(('center', final_video.h/2 + 100)).set_duration(audio_duration)
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main, txt_sub])
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    video_with_audio.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac")

# ================= 5. النشر مع صمام "الصبر" (الخطة الجديدة) =================
def publish_to_instagram(reciter_name, title):
    # إرسال الفيديو لتليجرام كنسخة احتياطية
    try:
        url_tg = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendVideo"
        with open('final_reel.mp4', 'rb') as video_file:
            requests.post(url_tg, data={'chat_id': ADMIN_CHAT_ID, 'caption': f"🎥 مقطع جاهز: {reciter_name}"}, files={'video': video_file}, timeout=200)
    except: pass

    cl = Client()
    cl.delay_range = [1, 3]
    
    caption = f"عافية لقلبك 🤍. تلاوة القارئ {reciter_name}. #قرآن #تلاوة #عافية_قلب"

    def login_process():
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
            return True
        except ChallengeRequired:
            # --- هنا السحر: البوت يطلب منك المساعدة وينتظرك ---
            alert = "⚠️ *تنبيه أمان إنستجرام*\n\nالبوت يواجه طلب تأكيد (كنت أنا من حاول الدخول). يرجى فتح تطبيق إنستجرام الآن والضغط على *'كنت أنا'*.\n\nسيقوم البوت بالانتظار لمدة *120 ثانية* ثم يعيد المحاولة تلقائياً!"
            send_telegram_alert(alert)
            print("⏳ تم اكتشاف طلب تأكيد. جاري الانتظار لمدة دقيقتين للموافقة اليدوية...")
            time.sleep(120) # الانتظار لمدة دقيقتين
            
            # المحاولة مرة ثانية بعد دقيقتين
            print("🔄 جاري إعادة المحاولة بعد الانتظار...")
            cl.login(IG_USERNAME, IG_PASSWORD)
            return True
        except Exception as e:
            raise e

    try:
        if login_process():
            cl.dump_settings(SESSION_FILE)
            print("✅ تم تسجيل الدخول! جاري الرفع...")
            cl.clip_upload("final_reel.mp4", caption)
            print("🎉 تم النشر بنجاح!")
    except Exception as e:
        raise Exception(f"❌ فشل النشر: {str(e)}")

# ================= التشغيل الرئيسي =================
if __name__ == "__main__":
    try:
        duration, title, vid_id, reciter = fetch_and_trim_audio()
        render_cinematic_video(duration, reciter)
        publish_to_instagram(reciter, title)
        
        history = load_history()
        history['used_videos'].append(vid_id)
        save_history(history)
        send_telegram_alert("✅ تم النشر بنجاح كامل!")
    except Exception as e:
        send_telegram_alert(f"⚠️ خطأ: {str(e)}")
        sys.exit(1)
