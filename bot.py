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
from instagrapi.exceptions import ChallengeRequired

# ================= الإعدادات والمفاتيح =================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
ERROR_BOT_TOKEN = os.environ.get("ERROR_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES")
HISTORY_FILE = "history.json"
SESSION_FILE = "session.json"

# ================= قنوات القراء =================
CHANNELS = [
    {"url": "https://www.youtube.com/@abdullahshaab1/videos", "name": "عبدالله شعبان"},
    {"url": "https://www.youtube.com/@9li9/videos", "name": "عبدالرحمن مسعد"}
]

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

# ================= 2. بروتوكول السرب الشامل (ليوتيوب) =================
def fetch_and_trim_audio():
    history = load_history()
    cookie_file = setup_cookies()
    
    ydl_opts_flat = {'quiet': True, 'extract_flat': True}
    if cookie_file: ydl_opts_flat['cookiefile'] = cookie_file
    
    forbidden_keywords = ['أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 'رقية', 'رقيّه', 'شرعية', 'دعاء', 'أدعية', 'بث مباشر']
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
    print("\n🚀 تفعيل بروتوكول السرب الشامل...")
    
    # المحاولة 1: التخفي بمتصفح كروم
    print("1️⃣ جاري السحب بتخفي كامل (Impersonate Chrome)...")
    ydl_opts_dl = {
        'format': 'ba/b/18', 'outtmpl': 'raw_audio.%(ext)s', 'quiet': True,
        'impersonate': 'chrome', 'extractor_args': {'youtube': ['player_client=android']},
    }
    if cookie_file: ydl_opts_dl['cookiefile'] = cookie_file
    try:
        with YoutubeDL(ydl_opts_dl) as ydl_dl:
            ydl_dl.download([video_url])
            downloaded = True
            print("🎉 تم التحميل بنجاح عبر التخفي!")
    except Exception as e: print(f"❌ فشل الهجوم المحلي: {e}")

    # المحاولة 2: Cobalt
    if not downloaded:
        print("2️⃣ جاري استدعاء أسطول Cobalt...")
        try:
            cobalt_req = requests.get("https://instances.hyper.lol/instances.json", timeout=15).json()
            cobalt_urls = [inst['url'] for inst in cobalt_req if inst.get('api_online')]
            random.shuffle(cobalt_urls)
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            payload = {"url": video_url, "isAudioOnly": True, "downloadMode": "audio", "aFormat": "mp3"}
            for api in cobalt_urls[:10]:
                try:
                    res = requests.post(f"{api}/", json=payload, headers=headers, timeout=20)
                    if res.status_code in [200, 202]:
                        dl_url = res.json().get('url')
                        if dl_url:
                            audio_data = requests.get(dl_url, timeout=300).content 
                            if len(audio_data) > 50000:
                                with open("raw_audio.mp3", "wb") as f: f.write(audio_data)
                                downloaded = True
                                print(f"🎉 تم التحميل بنجاح عبر Cobalt!")
                                break
                except Exception: continue
                if downloaded: break
        except Exception: print("تجاوز سرب Cobalt...")

    # المحاولة 3: Loader
    if not downloaded:
        print("3️⃣ جاري تفعيل غارة Loader הסحابية...")
        try:
            res = requests.get(f"https://loader.to/ajax/download.php?format=mp3&url={video_url}", timeout=20).json()
            job_id = res.get("id")
            if job_id:
                for _ in range(60): 
                    time.sleep(5)
                    status = requests.get(f"https://loader.to/ajax/progress.php?id={job_id}", timeout=15).json()
                    if status.get("text") == "Finished":
                        dl_url = status.get("download_url")
                        audio_data = requests.get(dl_url, timeout=300).content
                        if len(audio_data) > 50000:
                            with open("raw_audio.mp3", "wb") as f: f.write(audio_data)
                            downloaded = True
                            print("🎉 تم التحميل بنجاح عبر Loader!")
                            break
        except Exception: print("فشل Loader...")

    if not downloaded: raise Exception("جميع الأسراب السحابية والمحلية فشلت! الحظر اليوم جنوني.")

    print("\n✂️ جاري القص المسبق لحماية السيرفر...")
    full_audio = AudioFileClip("raw_audio.mp3") 
    short_audio_duration = min(60.0, full_audio.duration)
    short_audio = full_audio.subclip(0, short_audio_duration)
    short_audio.write_audiofile("short_audio.mp3", logger=None)
    full_audio.close()
    short_audio.close()

    print("🧠 جاري تحليل الصوت بالذكاء الاصطناعي...")
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe("short_audio.mp3", beam_size=5)
    
    end_time = 50.0 
    prev_end = 0
    for segment in segments:
        if segment.end > 40 and (segment.start - prev_end) > 1.2:
            end_time = prev_end
            break
        prev_end = segment.end
        if prev_end > 60:
            end_time = prev_end
            break

    final_audio = AudioFileClip("short_audio.mp3").subclip(0, end_time).audio_fadeout(2)
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    final_audio.close()
    try: os.remove("raw_audio.mp3")
    except: pass
    
    return end_time, video_title, vid_id, selected_reciter

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

# ================= 4. المونتاج السينمائي =================
def render_cinematic_video(audio_duration, reciter_name):
    clips = fetch_pexels_videos(audio_duration)
    final_video = concatenate_videoclips(clips, method="compose", padding=-1).subclip(0, audio_duration)
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    txt_main = TextClip("عافية قلب", font="taj.ttf", fontsize=80, color='white', stroke_color='black', stroke_width=2).set_position('center').set_duration(audio_duration).crossfadein(1)
    txt_sub = TextClip(f"القارئ: {reciter_name}", font="taj.ttf", fontsize=40, color='white').set_position(('center', final_video.h/2 + 100)).set_duration(audio_duration)
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main, txt_sub])
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    video_with_audio.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac", threads=4)

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
        print("تم إنهاء العملية بنجاح!")
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"\n❌ حدث خطأ فادح:\n{error_details}")
        send_telegram_alert(f"⚠️ خطأ:\n`{str(e)}`")
        sys.exit(1)
