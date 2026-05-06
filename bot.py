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

# ================= الإعدادات والمفاتيح =================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
INSTA_TOKEN = os.environ.get("INSTA_TOKEN")
ERROR_BOT_TOKEN = os.environ.get("ERROR_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES")
HISTORY_FILE = "history.json"

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

# ================= تجهيز الكوكيز =================
def setup_cookies():
    if YOUTUBE_COOKIES and len(YOUTUBE_COOKIES) > 10:
        with open("cookies.txt", "w") as f:
            f.write(YOUTUBE_COOKIES)
        return "cookies.txt"
    return None

# ================= 2. تحميل الفيديو واستخراج الصوت =================
def fetch_and_trim_audio():
    history = load_history()
    cookie_file = setup_cookies()
    
    # 1. إعدادات البحث
    ydl_opts_flat = {
        'quiet': True,
        'extract_flat': True,
    }
    if cookie_file:
        ydl_opts_flat['cookiefile'] = cookie_file
    
    forbidden_keywords = [
        'أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 
        'رقية', 'رقيّه', 'شرعية', 'شرعيه', 'دعاء', 'أدعية', 'ادعية', 
        'حصن المسلم', 'بث مباشر', 'مباشر الآن', 'برودكاست'
    ]
    
    selected_video = None
    selected_reciter = ""
    random.shuffle(CHANNELS)
    
    with YoutubeDL(ydl_opts_flat) as ydl:
        for channel in CHANNELS:
            print(f"جاري البحث في قناة: {channel['name']}...")
            try:
                info = ydl.extract_info(channel['url'], download=False)
                entries = info.get('entries', [])
                
                for entry in entries:
                    vid_id = entry.get('id', '')
                    title = entry.get('title', '')
                    
                    if not vid_id or not title: continue
                    
                    is_forbidden = any(word.lower() in title.lower() for word in forbidden_keywords)
                    
                    if len(vid_id) == 11 and vid_id not in history['used_videos'] and not is_forbidden:
                        selected_video = entry
                        selected_reciter = channel['name']
                        break
                
                if selected_video: break
            except Exception as e:
                print(f"خطأ في القناة: {e}")
                
    if not selected_video:
        raise Exception("لم أجد فيديوهات جديدة مناسبة في أي من القنوات!")

    vid_id = selected_video['id']
    video_title = selected_video['title']
    video_url = f"https://www.youtube.com/watch?v={vid_id}"
    print(f"تم اختيار: {video_title} (القارئ: {selected_reciter})")
    
    # 2. إعدادات التحميل (السلاح السري: نحمل الفيديو بدلاً من الصوت للتهرب من الحظر)
    ydl_opts_dl = {
        'format': '18/best', # صيغة 18 هي MP4 بجودة 360p (دائماً متاحة ولا يتم حجبها)
        'outtmpl': 'raw_media.%(ext)s',
        'quiet': True,
    }
    if cookie_file:
        ydl_opts_dl['cookiefile'] = cookie_file
        
    print("جاري سحب الملف من يوتيوب (بصيغة فيديو للتمويه)...")
    with YoutubeDL(ydl_opts_dl) as ydl_dl:
        info_dict = ydl_dl.extract_info(video_url, download=True)
        downloaded_file = ydl_dl.prepare_filename(info_dict)
        print("🎉 تم تحميل الملف بنجاح وتجاوز حجب الصوتيات!")

    # 3. استخراج الصوت وقصه
    print("جاري سلخ الصوت من الفيديو وقص أول 60 ثانية لحماية السيرفر...")
    full_media = AudioFileClip(downloaded_file) # يفتح الفيديو كأنه ملف صوتي
    short_audio_duration = min(60.0, full_media.duration)
    short_audio = full_media.subclip(0, short_audio_duration)
    short_audio.write_audiofile("short_audio.mp3", logger=None)
    full_media.close()
    
    # مسح الفيديو الأساسي لتوفير مساحة في السيرفر
    if os.path.exists(downloaded_file):
        os.remove(downloaded_file)

    # 4. تحليل الصوت
    print("جاري تحليل الصوت بالذكاء الاصطناعي...")
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

    print(f"سيتم القص النهائي عند الثانية: {end_time}")
    final_audio = AudioFileClip("short_audio.mp3").subclip(0, end_time).audio_fadeout(2)
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    final_audio.close()
    
    return end_time, video_title, vid_id, selected_reciter

# ================= 3. جلب فيديوهات الطبيعة =================
def fetch_pexels_videos(target_duration):
    today = datetime.now().strftime("%A")
    if today in ['Sunday', 'Tuesday', 'Thursday']:
        query = "drone landscape, nature, aerial view"
    else:
        query = "clouds, mountains, starry sky, peaceful nature"

    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&size=large&per_page=10"
    res = requests.get(url, headers=headers).json()
    
    video_files = []
    current_duration = 0
    for i, video in enumerate(res['videos']):
        if any(tag in str(video['tags']).lower() for tag in ['people', 'woman', 'face', 'human']):
            continue
        link = video['video_files'][0]['link']
        vid_data = requests.get(link).content
        vid_name = f"bg_vid_{i}.mp4"
        with open(vid_name, "wb") as f:
            f.write(vid_data)
        clip = VideoFileClip(vid_name)
        video_files.append(clip)
        current_duration += clip.duration
        if current_duration >= target_duration:
            break
    return video_files

# ================= 4. المونتاج السينمائي =================
def render_cinematic_video(audio_duration, reciter_name):
    clips = fetch_pexels_videos(audio_duration)
    final_video = concatenate_videoclips(clips, method="compose", padding=-1)
    final_video = final_video.subclip(0, audio_duration)
    
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    
    txt_main = TextClip("عافية قلب", font="taj.ttf", fontsize=80, color='white', stroke_color='black', stroke_width=2)
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1)
    
    txt_sub = TextClip(f"القارئ: {reciter_name}", font="taj.ttf", fontsize=40, color='white')
    txt_sub = txt_sub.set_position(('center', final_video.h/2 + 100)).set_duration(audio_duration)
    
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main, txt_sub])
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    video_with_audio.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac", threads=4)

# ================= 5. النشر في إنستجرام =================
def get_ig_account_id():
    url = f"https://graph.facebook.com/v18.0/me/accounts?access_token={INSTA_TOKEN}"
    res = requests.get(url).json()
    page_id = res['data'][0]['id']
    url2 = f"https://graph.facebook.com/v18.0/{page_id}?fields=instagram_business_account&access_token={INSTA_TOKEN}"
    res2 = requests.get(url2).json()
    return res2['instagram_business_account']['id']

def publish_to_instagram(reciter_name):
    upload_res = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': open('final_reel.mp4', 'rb')})
    temp_url = upload_res.json()['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
    
    ig_user_id = get_ig_account_id()
    today = datetime.now().strftime("%A")
    
    if today == 'Thursday':
        caption = "✨ سورة الكهف نور ما بين الجمعتين. لا تنسوا السنن والصلاة على النبي ﷺ. #سورة_الكهف #يوم_الجمعة #قرآن #تلاوة #عافية_قلب"
    else:
        caption = f"عافية لقلبك 🤍. أرح مسمعك بتلاوة القارئ {reciter_name}.\n\n#قرآن #تلاوة #راحة_نفسية #عافية_قلب #quran"

    media_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
    payload = {'media_type': 'REELS', 'video_url': temp_url, 'caption': caption, 'access_token': INSTA_TOKEN}
    creation_id = requests.post(media_url, data=payload).json()['id']
    
    time.sleep(35)
    publish_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish"
    requests.post(publish_url, data={'creation_id': creation_id, 'access_token': INSTA_TOKEN})

# ================= التشغيل الرئيسي =================
if __name__ == "__main__":
    try:
        duration, title, vid_id, reciter = fetch_and_trim_audio()
        render_cinematic_video(duration, reciter)
        publish_to_instagram(reciter)
        
        history = load_history()
        history['used_videos'].append(vid_id)
        save_history(history)
        
        success_message = f"✅ *بشارة من استوديو القرآن*\n\nتم إنتاج ونشر فيديو جديد بنجاح! 🎉\n\n*القارئ:* {reciter}\n*المقطع:* {title}\n*المدة:* {int(duration)} ثانية"
        send_telegram_alert(success_message)
        print("تم إنهاء العملية بنجاح كامل!")
        
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"\n❌ حدث خطأ فادح:\n{error_details}")
        error_message = f"⚠️ *تنبيه طارئ من استوديو القرآن*\n\nتوقف البوت عن العمل بسبب الخطأ التالي:\n\n`{str(e)}`\n\nيرجى الدخول لسيرفر GitHub للتحقق."
        send_telegram_alert(error_message)
        sys.exit(1)
