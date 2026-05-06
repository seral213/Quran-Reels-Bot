import os
import json
import time
import requests
import traceback
from datetime import datetime
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, TextClip, CompositeVideoClip, ColorClip

# ================= الإعدادات والمفاتيح =================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
INSTA_TOKEN = os.environ.get("INSTA_TOKEN")
ERROR_BOT_TOKEN = os.environ.get("ERROR_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
YOUTUBE_URL = "https://www.youtube.com/@abdullahshaab1"
HISTORY_FILE = "history.json"

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

# ================= 2. تحميل الصوت (محمي بدرع VPN) =================
def fetch_and_trim_audio():
    history = load_history()
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'raw_audio.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        'quiet': True,
        'extract_flat': True,
        'source_address': '0.0.0.0'
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        print("جاري جلب قائمة الفيديوهات من القناة...")
        info = ydl.extract_info(YOUTUBE_URL, download=False)
        entries = info['entries']
        
        selected_video = None
        for entry in entries:
            vid_id = entry.get('id', '')
            title = entry.get('title', '')
            # تم حذف كلمة 'ساعة' من الاستثناءات بناءً على طلبك
            if len(vid_id) == 11 and vid_id not in history['used_videos'] and not any(x in title for x in ['رقية', 'دعاء', 'بث', 'مباشر']):
                selected_video = entry
                break
                
        if not selected_video:
            raise Exception("لم أجد فيديوهات جديدة في القناة تستوفي الشروط!")

        vid_id = selected_video['id']
        video_title = selected_video['title']
        video_url = f"https://www.youtube.com/watch?v={vid_id}"
        print(f"تم اختيار: {video_title} (ID: {vid_id})")
        
        print("جاري سحب الصوت (تحت حماية Cloudflare WARP VPN)...")
        ydl_opts['extract_flat'] = False
        with YoutubeDL(ydl_opts) as ydl_dl:
            ydl_dl.download([video_url])
            
    print("جاري تحليل الصوت بالذكاء الاصطناعي...")
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe("raw_audio.mp3", beam_size=5)
    
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

    print(f"سيتم القص عند الثانية: {end_time}")
    audio = AudioFileClip("raw_audio.mp3").subclip(0, end_time).audio_fadeout(2)
    audio.write_audiofile("final_audio.mp3")
    
    return end_time, video_title, vid_id

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
def render_cinematic_video(audio_duration):
    clips = fetch_pexels_videos(audio_duration)
    final_video = concatenate_videoclips(clips, method="compose", padding=-1)
    final_video = final_video.subclip(0, audio_duration)
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    txt_main = TextClip("عافية قلب", font="taj.ttf", fontsize=80, color='white', stroke_color='black', stroke_width=2)
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1)
    txt_sub = TextClip("القارئ: عبدالله شعبان", font="taj.ttf", fontsize=40, color='white')
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

def publish_to_instagram():
    upload_res = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': open('final_reel.mp4', 'rb')})
    temp_url = upload_res.json()['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
    ig_user_id = get_ig_account_id()
    today = datetime.now().strftime("%A")
    caption = "✨ سورة الكهف ليلة الجمعة..." if today == 'Thursday' else "عافية لقلبك 🤍. أرح مسمعك.\n\n#قرآن #تلاوة #عبدالله_شعبان #عافية_قلب"
    media_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
    payload = {'media_type': 'REELS', 'video_url': temp_url, 'caption': caption, 'access_token': INSTA_TOKEN}
    creation_id = requests.post(media_url, data=payload).json()['id']
    time.sleep(35)
    publish_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish"
    requests.post(publish_url, data={'creation_id': creation_id, 'access_token': INSTA_TOKEN})

# ================= التشغيل الرئيسي =================
if __name__ == "__main__":
    import sys # استدعاء مكتبة النظام
    try:
        duration, title, vid_id = fetch_and_trim_audio()
        render_cinematic_video(duration)
        publish_to_instagram()
        
        # لا يتم تحديث الذاكرة إلا بعد نجاح النشر 100%
        history = load_history()
        history['used_videos'].append(vid_id)
        save_history(history)
        
        send_telegram_alert(f"✅ *تم النشر بنجاح!*\nالمقطع: {title}")
        print("تم إنهاء العملية بنجاح كامل!")
        
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"\n❌ حدث خطأ فادح:\n{error_details}")
        send_telegram_alert(f"⚠️ *خطأ:* `{str(e)}`")
        # هذا السطر هو الأهم: يجبر جيتهاب على إظهار الخطأ باللون الأحمر
        sys.exit(1) 
