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

# === استدعاءات إنستجرام ===
try:
    from instagrapi import Client
    from instagrapi.exceptions import ChallengeRequired
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
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES")
HISTORY_FILE = "history.json"
SESSION_FILE = "session.json"

# ================= دالة إصلاح النص العربي =================
def fix_arabic(text):
    if not text: return ""
    padded_text = f" {text} " 
    reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})
    reshaped_text = reshaper.reshape(padded_text)
    return get_display(reshaped_text)

# ================= قنوات القراء =================
CHANNELS = [
    {"url": "https://www.youtube.com/@abdullahshaab1/videos", "name": "عبدالله شعبان"},
    {"url": "https://www.youtube.com/@9li9/videos", "name": "عبدالرحمن مسعد"}
]

# ================= نظام إشعارات تليجرام =================
def send_telegram_alert(message):
    if not ERROR_BOT_TOKEN or not ADMIN_CHAT_ID: return
    url = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, data=payload)
    except Exception: pass

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                if "youtube_clips" not in data: data["youtube_clips"] = {}
                if "used_pexels" not in data: data["used_pexels"] = []
                return data
        except: pass
    return {"youtube_clips": {}, "used_pexels": []}

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

def setup_cookies():
    if YOUTUBE_COOKIES and len(YOUTUBE_COOKIES) > 10:
        with open("cookies.txt", "w") as f: f.write(YOUTUBE_COOKIES)
        return "cookies.txt"
    return None

# ================= بروتوكول السرب الشامل (الذاكرة الذكية) =================
def fetch_and_trim_audio():
    history = load_history()
    cookie_file = setup_cookies()
    
    ydl_opts_flat = {'quiet': True, 'extract_flat': True}
    if cookie_file: ydl_opts_flat['cookiefile'] = cookie_file
    
    forbidden_keywords = ['أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 'رقية', 'شرعية', 'دعاء', 'أدعية', 'بث مباشر']
    selected_video = None
    selected_reciter = ""
    start_time_for_clip = 0.0
    
    random.shuffle(CHANNELS)
    with YoutubeDL(ydl_opts_flat) as ydl:
        for channel in CHANNELS:
            print(f"جاري البحث في قناة: {channel['name']}...")
            try:
                info = ydl.extract_info(channel['url'], download=False)
                for entry in info.get('entries', []):
                    vid_id = entry.get('id', '')
                    title = entry.get('title', '')
                    duration_sec = entry.get('duration', 0)
                    
                    if not vid_id or not title or duration_sec == 0: continue
                    if any(word.lower() in title.lower() for word in forbidden_keywords): continue
                    
                    # --- الذكاء: فحص الذاكرة ---
                    saved_time = history['youtube_clips'].get(vid_id, 0.0)
                    if saved_time >= (duration_sec - 60): 
                        # الفيديو تم استهلاكه بالكامل (بقي أقل من دقيقة)
                        continue
                        
                    selected_video = entry
                    selected_reciter = channel['name']
                    start_time_for_clip = saved_time
                    break
                if selected_video: break
            except Exception as e: print(f"خطأ في القناة: {e}")
                
    if not selected_video: raise Exception("لم أجد فيديوهات فيها مساحة كافية للقص!")

    vid_id = selected_video['id']
    video_title = selected_video['title']
    video_url = f"https://www.youtube.com/watch?v={vid_id}"
    print(f"تم اختيار: {video_title}\nيبدأ القص من الدقيقة: {start_time_for_clip/60:.2f}")
    
    downloaded = False
    print("\n🚀 تفعيل بروتوكول السرب للتحميل...")
    
    ydl_opts_dl = {
        'format': 'ba/b/18/17/mp4/best',
        'outtmpl': 'raw_audio.%(ext)s', 'quiet': True,
        'impersonate': 'chrome', 'extractor_args': {'youtube': ['player_client=android']},
    }
    if cookie_file: ydl_opts_dl['cookiefile'] = cookie_file
    try:
        with YoutubeDL(ydl_opts_dl) as ydl_dl:
            ydl_dl.download([video_url])
            downloaded = True
            print("🎉 تم التحميل بنجاح محلياً!")
    except Exception as e: print(f"❌ فشل المحلي: {e}")

    # محاولة Cobalt و Loader محذوفة للتبسيط هنا (أضفها إذا أردت، لكن التخفي بمتصفح Chrome كافٍ جداً الآن مع الجودات المتعددة).
    if not downloaded:
        try:
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            payload = {"url": video_url, "isAudioOnly": True, "aFormat": "mp3"}
            res = requests.post("https://api.cobalt.tools/api/json", json=payload, headers=headers, timeout=20)
            if res.status_code == 200 and res.json().get('url'):
                audio_data = requests.get(res.json().get('url'), timeout=300).content
                if len(audio_data) > 50000:
                    with open("raw_audio.mp3", "wb") as f: f.write(audio_data)
                    downloaded = True
        except: pass

    if not downloaded: raise Exception("جميع الأسراب السحابية والمحلية فشلت! الحظر جنوني اليوم.")

    print("🧠 جاري تحليل الصوت بالذكاء الاصطناعي...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    full_audio_clip = AudioFileClip("raw_audio.mp3")
    
    # أخذ عينة دقيقتين من نقطة التوقف السابقة
    analysis_end = min(start_time_for_clip + 120.0, full_audio_clip.duration)
    analysis_subclip = full_audio_clip.subclip(start_time_for_clip, analysis_end)
    analysis_subclip.write_audiofile("temp_analysis.mp3", logger=None)
    
    segments, info = model.transcribe("temp_analysis.mp3", beam_size=5, word_timestamps=True)
    segments_list = list(segments)
    try: os.remove("temp_analysis.mp3")
    except: pass

    relative_start = 0.0
    # فقط نبحث عن مقدمة إذا كنا في بداية الفيديو (الثانية 0)
    if start_time_for_clip == 0.0:
        intro_keywords = ["بسم الله", "أعوذ بالله", "الحمد لله", "رب العالمين"]
        for segment in segments_list:
            if any(word in segment.text for word in intro_keywords) and segment.start < 60.0:
                relative_start = segment.start
                print(f"✅ تم تخطي المقدمة.")
                break

    relative_end = min(relative_start + 60.0, analysis_subclip.duration)
    best_gap = 0
    for i in range(len(segments_list) - 1):
        curr = segments_list[i]
        nxt = segments_list[i+1]
        if curr.end > (relative_start + 45.0) and curr.end < relative_end:
            gap = nxt.start - curr.end
            if gap > 1.2 and gap > best_gap:
                best_gap = gap
                relative_end = curr.end + (gap / 2)
                break

    # حساب الأوقات الحقيقية بالنسبة للفيديو الأصلي
    absolute_start = start_time_for_clip + relative_start
    absolute_end = start_time_for_clip + relative_end
    
    # --- تحديث الذاكرة للنقطة الجديدة ---
    history['youtube_clips'][vid_id] = absolute_end
    
    final_audio_duration = absolute_end - absolute_start
    trimmed_audio = full_audio_clip.subclip(absolute_start, absolute_end)
    final_audio = trimmed_audio.audio_fadein(1.0).audio_fadeout(1.5)
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    
    final_audio.close()
    full_audio_clip.close()
    try: os.remove("raw_audio.mp3")
    except: pass
    
    return final_audio_duration, video_title, vid_id, selected_reciter, history

# ================= 3. جلب فيديوهات الطبيعة (الدوران الذكي) =================
def fetch_pexels_videos(target_duration, history):
    today = datetime.now().strftime("%A")
    query = "drone landscape, nature" if today in ['Sunday', 'Tuesday', 'Thursday'] else "clouds, peaceful nature"
    
    # البحث في صفحات عشوائية لتنويع النتائج
    random_page = random.randint(1, 3)
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&size=large&per_page=30&page={random_page}"
    res_data = requests.get(url, headers=headers).json()
    
    if 'videos' not in res_data: raise Exception(f"خطأ Pexels: {res_data}")
        
    video_files = []
    current_duration = 0
    
    for video in res_data['videos']:
        vid_id_str = str(video['id'])
        # تخطي الفيديو إذا كان في الذاكرة (تم استخدامه قريباً)
        if vid_id_str in history['used_pexels']: continue
        if any(tag in str(video['tags']).lower() for tag in ['people', 'woman', 'face']): continue
        
        link = video['video_files'][0]['link']
        vid_data = requests.get(link).content
        vid_name = f"bg_vid_{vid_id_str}.mp4"
        
        with open(vid_name, "wb") as f: f.write(vid_data)
        clip = VideoFileClip(vid_name)
        video_files.append((clip, vid_name))
        current_duration += clip.duration
        
        # حفظ الفيديو في الذاكرة وإزالة القديم إذا تجاوز 60 فيديو
        history['used_pexels'].append(vid_id_str)
        if len(history['used_pexels']) > 60:
            history['used_pexels'].pop(0)
            
        if current_duration >= target_duration: break
        
    return video_files, history

# ================= 4. المونتاج السينمائي (النص المخفف) =================
def render_cinematic_video(audio_duration, clips_data):
    clips = [data[0] for data in clips_data]
    final_video = concatenate_videoclips(clips, method="compose", padding=-1).subclip(0, audio_duration)
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    
    # --- إبقاء عنوان عافية قلب فقط بناء على طلبك وإزالة اسم القارئ ---
    box_width = int(final_video.w * 0.9)
    reshaped_main_title = fix_arabic("عافية قلب")
    
    txt_main = TextClip(reshaped_main_title, font="taj.ttf", fontsize=28, color='white', stroke_color='black', stroke_width=1, size=(box_width, None), method='caption', align='center')
    # توسيط النص تماماً في الشاشة
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1.0)
    
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main])
    video_with_audio = video_with_audio.fadein(1.0).fadeout(1.5)
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    video_with_audio.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac", threads=4)
    
    video_with_audio.close()
    final_video.close()
    dark_overlay.close()
    for clip, name in clips_data:
        try: os.remove(name)
        except: pass

# ================= 5. صمام النشر لإنستجرام =================
def publish_to_instagram(reciter_name, title):
    print("جاري الإرسال لتليجرام...")
    try:
        url_tg = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendVideo"
        with open('final_reel.mp4', 'rb') as video_file:
            requests.post(url_tg, data={'chat_id': ADMIN_CHAT_ID, 'caption': f"🎥 مقطع جاهز!\n\nالقارئ: {reciter_name}\nالعنوان: {title}"}, files={'video': video_file}, timeout=200)
    except: pass

    if not IG_USERNAME or not IG_PASSWORD: raise Exception("الـ Secrets مفقودة!")
    caption = f"عافية لقلبك 🤍. أرح مسمعك بتلاوة القارئ {reciter_name}.\n\n#قرآن #تلاوة #عافية_قلب"
    
    cl = Client()
    cl.delay_range = [1, 3]

    def login_process():
        if os.path.exists(SESSION_FILE): cl.load_settings(SESSION_FILE)
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
            return True
        except ChallengeRequired:
            alert = "⚠️ *تنبيه إنستجرام*\n\nيرجى الدخول لتطبيق إنستجرام والضغط على *'كنت أنا'*. البوت سينتظر دقيقتين ثم يعاود المحاولة."
            send_telegram_alert(alert)
            time.sleep(120)
            cl.login(IG_USERNAME, IG_PASSWORD)
            return True
        except Exception as e: raise e

    try:
        if login_process():
            cl.dump_settings(SESSION_FILE)
            cl.clip_upload("final_reel.mp4", caption)
            print("🎉 تم النشر بنجاح!")
    except Exception as e:
        raise Exception(f"❌ فشل النشر: {str(e)}")

# ================= التشغيل الرئيسي (إلحاح متكرر) =================
if __name__ == "__main__":
    max_retries = 3 
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n🚀 --- بدء محاولة التشغيل {attempt}/3 ---")
            
            dur, title, vid_id, reciter, history = fetch_and_trim_audio()
            clips_data, updated_history = fetch_pexels_videos(dur, history)
            render_cinematic_video(dur, clips_data)
            publish_to_instagram(reciter, title)
            
            # حفظ الذاكرة الشاملة المحدثة (يوتيوب وبيكسلز)
            save_history(updated_history)
            send_telegram_alert("✅ تم النشر بنجاح كامل!")
            break 
            
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"\n❌ حدث خطأ في المحاولة {attempt}:\n{error_details}")
            if attempt < max_retries:
                send_telegram_alert(f"⚠️ فشل (المحاولة {attempt}). جاري انتظار 3 دقائق...")
                time.sleep(180)
            else:
                send_telegram_alert(f"🚨 *فشل نهائي*\n\n`{str(e)}`")
                sys.exit(1)
