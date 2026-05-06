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
ERROR_BOT_TOKEN = os.environ.get("ERROR_BOT_TOKEN") # توكن بوت التنبيهات
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")     # الآي دي الشخصي الخاص بك في تليجرام
YOUTUBE_URL = "https://www.youtube.com/@abdullahshaab1"
HISTORY_FILE = "history.json"

# ================= 0. نظام إشعارات الأخطاء (الجديد) =================
def send_error_to_telegram(error_message):
    if not ERROR_BOT_TOKEN or not ADMIN_CHAT_ID:
        print("تنبيه: لم يتم العثور على مفاتيح تليجرام لإرسال الخطأ.")
        return
    
    url = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendMessage"
    msg = f"⚠️ *تنبيه طارئ من استوديو القرآن*\n\nتوقف البوت عن العمل بسبب الخطأ التالي:\n\n`{error_message}`\n\nيرجى الدخول لسيرفر GitHub للتحقق والتحديث."
    payload = {"chat_id": ADMIN_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload)
        print("تم إرسال إشعار الخطأ إلى تليجرام بنجاح.")
    except Exception as e:
        print(f"فشل إرسال إشعار الخطأ لتليجرام: {e}")

# ================= 1. نظام الذاكرة =================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                # التأكد من وجود المفتاح حتى لو كان الملف موجوداً
                if "used_videos" not in data:
                    data["used_videos"] = []
                return data
        except:
            return {"used_videos": []}
    return {"used_videos": []}

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

# ================= 2. تحميل الصوت والقص بالذكاء الاصطناعي =================
def fetch_and_trim_audio():
    history = load_history()
    
    # نستخدم yt-dlp فقط لقراءة "أسماء" الفيديوهات من القناة (هذا لا يتم حظره)
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        print("جاري جلب قائمة الفيديوهات من القناة...")
        info = ydl.extract_info(YOUTUBE_URL, download=False)
        entries = info['entries']
        
        selected_video = None
        for entry in entries:
            vid_id = entry['id']
            title = entry.get('title', '')
            # تخطي الفيديوهات المستخدمة والكلمات المستثناة
            if vid_id not in history['used_videos'] and not any(x in title for x in ['رقية', 'ساعة', 'دعاء']):
                selected_video = entry
                break
                
        if not selected_video:
            raise Exception("لم أجد فيديوهات جديدة في القناة!")

        print(f"تم اختيار: {selected_video['title']}")
        vid_id = selected_video['id']
        video_url = f"https://www.youtube.com/watch?v={vid_id}"
        
        # ----------------- فكرتك العبقرية: استخدام موقع تحميل خارجي -----------------
        print("جاري إرسال الرابط لموقع التحميل الخارجي (Cobalt API)...")
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # إعدادات الطلب للموقع الخارجي (نطلب منه الصوت فقط بصيغة mp3)
        payload = {
            "url": video_url,
            "downloadMode": "audio",
            "aFormat": "mp3",
            "isAudioOnly": True
        }
        
        try:
            # نرسل الرابط للموقع
            res = requests.post("https://api.cobalt.tools/", json=payload, headers=headers)
            
            # إذا كان السيرفر الأساسي مشغولاً، نستخدم السيرفر البديل لنفس الموقع
            if res.status_code != 200:
                res = requests.post("https://co.wuk.sh/api/json", json=payload, headers=headers)
                
            data = res.json()
            
            if 'url' in data:
                audio_url = data['url']
                print("✅ الموقع الخارجي جهز الملف! جاري تحميل الصوت المباشر...")
                
                # تحميل الملف الصوتي الذي أعطانا إياه الموقع
                audio_data = requests.get(audio_url, timeout=60).content
                with open("raw_audio.mp3", "wb") as f:
                    f.write(audio_data)
                print("🎉 تم تحميل الصوت بنجاح بفضل فكرتك!")
            else:
                raise Exception("الموقع الخارجي لم يستطع معالجة الرابط.")
                
        except Exception as e:
            print(f"تفاصيل الخطأ: {e}")
            raise Exception("فشلت حيلة الموقع الخارجي، يبدو أن يوتيوب يشن حرباً اليوم!")
        # -------------------------------------------------------------------------
            
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
    
    history['used_videos'].append(vid_id)
    save_history(history)
    return end_time

# ================= 3. جلب فيديوهات الطبيعة (متعددة) =================
def fetch_pexels_videos(target_duration):
    today = datetime.now().strftime("%A")
    # يومين في الأسبوع للدرون، والباقي طبيعة خلابة
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
        # التأكد أنه ليس به أشخاص (بناءً على التاجز)
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
    
    print("جاري دمج الفيديوهات وإضافة الانتقالات (Crossfade)...")
    # دمج الفيديوهات مع انتقالة Fade بين كل فيديو
    final_video = concatenate_videoclips(clips, method="compose", padding=-1)
    
    # قص الفيديو ليتطابق مع طول الصوت تماماً
    final_video = final_video.subclip(0, audio_duration)
    
    # إضافة الفلتر السينمائي (طبقة داكنة بنسبة 35%)
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    
    # إضافة النص (عافية قلب)
    txt_main = TextClip("عافية قلب", font="taj.ttf", fontsize=80, color='white', stroke_color='black', stroke_width=2)
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1)
    
    txt_sub = TextClip("القارئ: عبدالله شعبان", font="taj.ttf", fontsize=40, color='white')
    txt_sub = txt_sub.set_position(('center', final_video.h/2 + 100)).set_duration(audio_duration)
    
    # دمج كل شيء
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main, txt_sub])
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    
    print("تصدير الفيديو النهائي...")
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
    print("رفع الفيديو إلى سيرفر مؤقت لإنستجرام...")
    upload_res = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': open('final_reel.mp4', 'rb')})
    temp_url = upload_res.json()['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
    
    ig_user_id = get_ig_account_id()
    
    today = datetime.now().strftime("%A")
    if today == 'Thursday':
        caption = "✨ سورة الكهف نور ما بين الجمعتين. لا تنسوا السنن والصلاة على النبي ﷺ. #سورة_الكهف #يوم_الجمعة #قرآن #تلاوة #عافية_قلب"
    else:
        caption = "عافية لقلبك 🤍. أرح مسمعك.\n\n#قرآن #تلاوة #راحة_نفسية #عبدالله_شعبان #عافية_قلب #quran"

    print("جاري إرسال طلب النشر لإنستجرام...")
    media_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
    payload = {'media_type': 'REELS', 'video_url': temp_url, 'caption': caption, 'access_token': INSTA_TOKEN}
    creation_res = requests.post(media_url, data=payload).json()
    
    if 'error' in creation_res:
        raise Exception(f"خطأ من إنستجرام أثناء التجهيز: {creation_res['error']['message']}")
        
    creation_id = creation_res['id']
    
    print("الانتظار 30 ثانية ليعالج إنستجرام الفيديو...")
    time.sleep(30)
    
    publish_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish"
    publish_payload = {'creation_id': creation_id, 'access_token': INSTA_TOKEN}
    final_res = requests.post(publish_url, data=publish_payload).json()
    
    if 'error' in final_res:
        raise Exception(f"خطأ من إنستجرام أثناء النشر: {final_res['error']['message']}")
        
    print(f"تم النشر بنجاح! ID: {final_res.get('id')}")

# ================= التشغيل الرئيسي (مع مراقب الأخطاء) =================
if __name__ == "__main__":
    try:
        duration = fetch_and_trim_audio()
        render_cinematic_video(duration)
        publish_to_instagram()
    except Exception as e:
        error_details = traceback.format_exc() # لجلب تفاصيل الخطأ برمجياً بشكل دقيق
        print(f"\n❌ حدث خطأ فادح:\n{error_details}")
        # إرسال الخطأ إلى تليجرام فوراً قبل إغلاق السيرفر
        send_error_to_telegram(str(e))

