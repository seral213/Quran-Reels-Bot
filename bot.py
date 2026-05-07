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

# === استدعاءات إنستجرام وتعديل العربي ===
try:
    from instagrapi import Client
    from instagrapi.exceptions import ChallengeRequired
except ImportError:
    raise Exception("❌ مكتبة instagrapi غير مثبتة. تأكد من وجودها في ملف requirements.txt")

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
    reshaper = arabic_reshaper.ArabicReshaper(configuration={
        'delete_harakat': False,
        'support_ligatures': True,
    })
    reshaped_text = reshaper.reshape(padded_text)
    bidi_text = get_display(reshaped_text)
    return bidi_text

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
                if "used_videos" not in data: data["used_videos"] = []
                return data
        except: return {"used_videos": []}
    return {"used_videos": []}

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

def setup_cookies():
    if YOUTUBE_COOKIES and len(YOUTUBE_COOKIES) > 10:
        with open("cookies.txt", "w") as f: f.write(YOUTUBE_COOKIES)
        return "cookies.txt"
    return None

# ================= بروتوكول السرب الشامل =================
def fetch_and_trim_audio():
    history = load_history()
    cookie_file = setup_cookies()
    
    ydl_opts_flat = {'quiet': True, 'extract_flat': True}
    if cookie_file: ydl_opts_flat['cookiefile'] = cookie_file
    
    forbidden_keywords = ['أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 'رقية', 'شرعية', 'دعاء', 'أدعية', 'بث مباشر']
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
                    if not vid_id or not title: continue
                    is_forbidden = any(word.lower() in title.lower() for word in forbidden_keywords)
                    if len(vid_id) == 11 and vid_id not in history['used_videos'] and not is_forbidden:
                        selected_video = entry
                        selected_reciter = channel['name']
                        break
                if selected_video: break
            except Exception as e: print(f"خطأ في القناة: {e}")
                
    if not selected_video: raise Exception("لم أجد فيديوهات جديدة مناسبة!")

    vid_id = selected_video['id']
    video_title = selected_video['title']
    video_url = f"https://www.youtube.com/watch?v={vid_id}"
    print(f"تم اختيار: {video_title} (القارئ: {selected_reciter})")
    
    downloaded = False
    print("\n🚀 تفعيل بروتوكول السرب...")
    
    # المحاولة 1: التخفي المحلي
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
            print("🎉 تم التحميل بنجاح عبر التخفي المحلي!")
    except Exception as e: print(f"❌ فشل المحلي: {e}")

    # المحاولة 2: Cobalt הסحابي
    if not downloaded:
        try:
            cobalt_req = requests.get("https://instances.hyper.lol/instances.json", timeout=15).json()
            cobalt_urls = [inst['url'] for inst in cobalt_req if inst.get('api_online')]
            random.shuffle(cobalt_urls)
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            payload = {"url": video_url, "isAudioOnly": True, "aFormat": "mp3"}
            for api in cobalt_urls[:5]:
                try:
                    res = requests.post(f"{api}/", json=payload, headers=headers, timeout=20)
                    if res.status_code in [200, 202] and res.json().get('url'):
                        audio_data = requests.get(res.json().get('url'), timeout=300).content 
                        if len(audio_data) > 50000:
                            with open("raw_audio.mp3", "wb") as f: f.write(audio_data)
                            downloaded = True
                            print("🎉 تم التحميل بنجاح عبر Cobalt הסحابي!")
                            break
                except: continue
                if downloaded: break
        except: pass

    # المحاولة 3: Loader السحابي
    if not downloaded:
        try:
            res = requests.get(f"https://loader.to/ajax/download.php?format=mp3&url={video_url}", timeout=20).json()
            job_id = res.get("id")
            if job_id:
                for _ in range(60): 
                    time.sleep(5)
                    status = requests.get(f"https://loader.to/ajax/progress.php?id={job_id}", timeout=15).json()
                    if status.get("text") == "Finished":
                        audio_data = requests.get(status.get("download_url"), timeout=300).content
                        if len(audio_data) > 50000:
                            with open("raw_audio.mp3", "wb") as f: f.write(audio_data)
                            downloaded = True
                            print("🎉 تم التحميل بنجاح عبر Loader السحابي!")
                            break
        except: pass

    if not downloaded: raise Exception("جميع الأسراب السحابية والمحلية فشلت! الحظر جنوني اليوم.")

    # --- بداية المونتاج الذكي ---
    print("🧠 جاري تحليل الصوت بالذكاء الاصطناعي (Whisper base)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    full_audio_clip = AudioFileClip("raw_audio.mp3")
    analysis_end = min(120.0, full_audio_clip.duration)
    full_audio_clip.subclip(0, analysis_end).write_audiofile("temp_analysis.mp3", logger=None)
    full_audio_clip.close()

    segments, info = model.transcribe("temp_analysis.mp3", beam_size=5, word_timestamps=True)
    segments_list = list(segments)
    
    try: os.remove("temp_analysis.mp3")
    except: pass

    actual_start_time = 0.0
    intro_keywords = ["بسم الله", "أعوذ بالله", "الحمد لله", "رب العالمين"]
    
    for segment in segments_list:
        is_recitation_start = any(word in segment.text for word in intro_keywords)
        if is_recitation_start and segment.start < 60.0:
            actual_start_time = segment.start
            print(f"✅ تم تخطي المقدمة. البداية الحقيقية: {actual_start_time:.2f}")
            break

    target_absolute_end = actual_start_time + 50.0
    actual_end_time = min(actual_start_time + 60.0, full_audio_clip.duration)

    best_gap_duration = 0
    for i in range(len(segments_list) - 1):
        current_segment = segments_list[i]
        next_segment = segments_list[i+1]
        
        if current_segment.end > (actual_start_time + 45.0) and current_segment.end < actual_end_time:
            gap_duration = next_segment.start - current_segment.end
            if gap_duration > 1.2 and gap_duration > best_gap_duration:
                best_gap_duration = gap_duration
                actual_end_time = current_segment.end + (gap_duration / 2)
                break

    final_audio_duration = actual_end_time - actual_start_time
    
    re_opened_audio = AudioFileClip("raw_audio.mp3")
    trimmed_audio = re_opened_audio.subclip(actual_start_time, actual_end_time)
    final_audio = trimmed_audio.audio_fadein(1.0).audio_fadeout(1.5)
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    
    final_audio.close()
    re_opened_audio.close()
    try: os.remove("raw_audio.mp3")
    except: pass
    
    return final_audio_duration, video_title, vid_id, selected_reciter

# ================= 3. جلب فيديوهات الطبيعة =================
def fetch_pexels_videos(target_duration):
    today = datetime.now().strftime("%A")
    query = "drone landscape, nature" if today in ['Sunday', 'Tuesday', 'Thursday'] else "clouds, peaceful nature"
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&size=large&per_page=10"
    res_data = requests.get(url, headers=headers).json()
    if 'videos' not in res_data: raise Exception(f"خطأ Pexels: {res_data}")
        
    video_files = []
    current_duration = 0
    for i, video in enumerate(res_data['videos']):
        if any(tag in str(video['tags']).lower() for tag in ['people', 'woman', 'face']): continue
        link = video['video_files'][0]['link']
        vid_data = requests.get(link).content
        with open(f"bg_vid_{i}.mp4", "wb") as f: f.write(vid_data)
        clip = VideoFileClip(f"bg_vid_{i}.mp4")
        video_files.append(clip)
        current_duration += clip.duration
        if current_duration >= target_duration: break
    return video_files

# ================= 4. المونتاج السينمائي (مع صندوق النص الذكي) =================
def render_cinematic_video(audio_duration, reciter_name):
    clips = fetch_pexels_videos(audio_duration)
    final_video = concatenate_videoclips(clips, method="compose", padding=-1).subclip(0, audio_duration)
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    
    # إنشاء صندوق وهمي للنص بعرض 90% من الشاشة لمنع القص نهائياً
    box_width = int(final_video.w * 0.9)
    
    reshaped_main_title = fix_arabic("عافية قلب")
    # تم تغيير method إلى 'caption' وتحديد size وإضافة align='center' لمنع التقطيع
    txt_main = TextClip(reshaped_main_title, font="taj.ttf", fontsize=35, color='white', stroke_color='black', stroke_width=1.5, size=(box_width, None), method='caption', align='center')
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1.0)
    
    reshaped_sub_title = fix_arabic(f"القارئ: {reciter_name}")
    # تصغير خط القارئ إلى 20
    txt_sub = TextClip(reshaped_sub_title, font="taj.ttf", fontsize=20, color='white', size=(box_width, None), method='caption', align='center')
    txt_sub = txt_sub.set_position(('center', final_video.h/2 + 70)).set_duration(audio_duration).crossfadein(1.0)
    
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main, txt_sub])
    video_with_audio = video_with_audio.fadein(1.0).fadeout(1.5)
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    video_with_audio.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac", threads=4)
    
    video_with_audio.close()
    final_video.close()
    dark_overlay.close()
    for i in range(len(clips)):
        try: os.remove(f"bg_vid_{i}.mp4")
        except: pass

# ================= 5. صمام النشر لإنستجرام =================
def publish_to_instagram(reciter_name, title):
    print("جاري الإرسال لتليجرام...")
    try:
        url_tg = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendVideo"
        with open('final_reel.mp4', 'rb') as video_file:
            requests.post(url_tg, data={'chat_id': ADMIN_CHAT_ID, 'caption': f"🎥 مقطع جاهز!\n\nالقارئ: {reciter_name}\nالعنوان: {title}"}, files={'video': video_file}, timeout=200)
    except Exception as e: print(f"⚠️ خطأ في تليجرام: {e}")

    if not IG_USERNAME or not IG_PASSWORD: raise Exception("الـ Secrets مفقودة!")
    
    caption = f"عافية لقلبك 🤍. أرح مسمعك بتلاوة القارئ {reciter_name}.\n\n#قرآن #تلاوة #عافية_قلب"
    print("جاري تسجيل الدخول لإنستجرام...")
    
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
            print("⏳ تم اكتشاف طلب تأكيد. جاري الانتظار 120 ثانية...")
            time.sleep(120)
            print("🔄 جاري المحاولة مرة أخرى...")
            cl.login(IG_USERNAME, IG_PASSWORD)
            return True
        except Exception as e: raise e

    try:
        if login_process():
            cl.dump_settings(SESSION_FILE)
            print("✅ تم الدخول! جاري الرفع...")
            cl.clip_upload("final_reel.mp4", caption)
            print("🎉 تم النشر بنجاح!")
    except Exception as e:
        raise Exception(f"❌ فشل النشر: {str(e)}")

# ================= التشغيل الرئيسي (مع نظام الإلحاح 🔄) =================
if __name__ == "__main__":
    max_retries = 3 # عدد محاولات التشغيل الكلية إذا فشل التحميل
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n🚀 --- بدء محاولة التشغيل رقم {attempt} من {max_retries} ---")
            
            duration, title, vid_id, reciter = fetch_and_trim_audio()
            render_cinematic_video(duration, reciter)
            publish_to_instagram(reciter, title)
            
            history = load_history()
            history['used_videos'].append(vid_id)
            save_history(history)
            
            send_telegram_alert("✅ تم النشر بنجاح كامل!")
            print("تم إنهاء العملية بنجاح كامل!")
            break # الخروج من الحلقة بنجاح
            
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"\n❌ حدث خطأ في المحاولة {attempt}:\n{error_details}")
            
            if attempt < max_retries:
                alert_msg = f"⚠️ واجه البوت مشكلة في المحاولة {attempt}.\nجاري الانتظار 3 دقائق وإعادة المحاولة...\n\nالخطأ:\n{str(e)}"
                send_telegram_alert(alert_msg)
                print("⏳ جاري الانتظار 3 دقائق قبل المحاولة التالية لتجنب الحظر...")
                time.sleep(180) # انتظار 3 دقائق
            else:
                final_error = f"🚨 *فشل نهائي*\n\nفشلت جميع المحاولات الـ {max_retries} اليوم!\n\nالخطأ الأخير:\n`{str(e)}`\n\nيرجى الدخول لسيرفر GitHub للتحقق."
                send_telegram_alert(final_error)
                sys.exit(1)
