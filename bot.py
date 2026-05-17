import os
import sys

# التحديث التلقائي الإجباري لمكتبة yt-dlp
print("🔄 جاري فحص وتحديث مكتبة yt-dlp لأحدث إصدار عالمي...")
os.system(f"{sys.executable} -m pip install -U yt-dlp --quiet")

import json
import time
import random
import requests
import traceback
import re
import glob
import urllib3
from datetime import datetime

# الرقعة البرمجية لإصلاح مكتبة الصور ومشاكل الشفافية
from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, TextClip, CompositeVideoClip, ColorClip
from moviepy.video.fx.all import crop, resize

try:
    from instagrapi import Client
except ImportError:
    raise Exception("❌ مكتبة instagrapi غير مثبتة.")

import arabic_reshaper
from bidi.algorithm import get_display

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= الإعدادات والمفاتيح =================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
ERROR_BOT_TOKEN = os.environ.get("ERROR_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY") # القائد الجديد وحش اللغة العربية
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SESSION_FILE = "session.json"

RECITERS = ["عبدالرحمن مسعد", "ياسر الدوسري", "عبدالله شعبان"]
SURAHS_DICT = {
    "الكهف": 18, "مريم": 19, "طه": 20, "الأنبياء": 21, "النور": 24, "الفرقان": 25, 
    "يس": 36, "الصافات": 37, "غافر": 40, "الرحمن": 55, "الواقعة": 56, "الملك": 67, 
    "القيامة": 75, "الإنسان": 76, "النبأ": 78, "النازعات": 79, "عبس": 80, 
    "التكوير": 81, "الأعلى": 87, "الغاشية": 88, "الفجر": 89, "الضحى": 93, "يوسف": 12
}

def send_telegram_alert(message):
    if not ERROR_BOT_TOKEN or not ADMIN_CHAT_ID: return
    url = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, data=payload)
    except: pass

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

# ================= 🧠 العقول المجانية المفتوحة =================
def get_smart_timestamps(transcript_segments, max_duration):
    if not transcript_segments: return None, None, "لم يتم استخراج نص."

    full_text_with_time = "".join([f"[{seg.start:.2f} - {seg.end:.2f}]: {seg.text}\n" for seg in transcript_segments])
    prompt = f"""أنت خبير في المونتاج القرآني.
أمامك نص تلاوة مع التوقيت الزمني (بالثواني).
اختر نقطة بداية ونقطة نهاية بحيث تبدأ بآية وتنتهي بآية تامة المعنى. يجب أن يكون طول المقطع بين 40 و 58 ثانية.
النص:
{full_text_with_time}
الرد يجب أن يكون فقط مصفوفة أرقام بهذا الشكل بالضبط:
[15.5, 65.2]
يُمنع منعاً باتاً كتابة أي حرف إضافي.
"""
    
    # 1️⃣ القائد: Cohere (وحش اللغة العربية)
    if COHERE_API_KEY:
        try:
            print("🧠 جاري محاولة القص عبر القائد (Cohere - Command-R)...")
            api_url = "https://api.cohere.ai/v1/chat"
            headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
            payload = {"message": prompt, "model": "command-r", "temperature": 0.0}
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                text_response = response.json().get('text', '')
                print(f"🤖 رد Cohere: {text_response.strip()}")
                nums = re.findall(r'[0-9]+(?:\.[0-9]+)?', text_response)
                if len(nums) >= 2: return float(nums[0]), float(nums[1]), None
            else:
                print(f"⚠️ فشل Cohere (الكود: {response.status_code}). سيتم الانتقال للبديل.")
        except Exception as e: print(f"⚠️ خطأ في Cohere: {e}")

    # 2️⃣ البديل: Groq (تم تحديث اسم النموذج ليعمل بدون خطأ 400)
    if GROQ_API_KEY:
        try:
            print("🔄 تفعيل المحرك الاحتياطي (Groq - Llama 3.1 8B)...")
            groq_url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            # ✅ تحديث الجيل إلى أحدث نسخة تعمل بكفاءة
            payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0}
            response = requests.post(groq_url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                text_response = response.json()['choices'][0]['message']['content']
                print(f"🤖 رد Groq: {text_response.strip()}")
                nums = re.findall(r'[0-9]+(?:\.[0-9]+)?', text_response)
                if len(nums) >= 2: return float(nums[0]), float(nums[1]), None
            else:
                print(f"❌ فشل Groq (الكود: {response.status_code}).")
        except Exception as e: print(f"❌ خطأ في Groq: {e}")

    return None, None, "فشلت جميع محركات الذكاء الاصطناعي."

def fix_arabic(text):
    if not text: return ""
    reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})
    return get_display(reshaper.reshape(f" {text} "))

def get_mp3quran_live_url(reciter_name, surah_number):
    print("📡 جاري الاتصال بقاعدة بيانات MP3Quran لاستخراج الرابط الحي المحدث...")
    api_url = "https://mp3quran.net/api/v3/reciters?language=ar"
    try:
        res = requests.get(api_url, timeout=15, verify=False).json()
        for reciter in res.get('reciters', []):
            if reciter_name in reciter.get('name', ''):
                for moshaf in reciter.get('moshaf', []):
                    server_url = moshaf.get('server', '')
                    if server_url:
                        if not server_url.endswith('/'): server_url += '/'
                        final_url = f"{server_url}{surah_number:03d}.mp3"
                        return final_url
    except Exception as e: print(f"❌ فشل الاتصال بـ MP3Quran API: {e}")
    return None

def download_url_safe(url, ext="mp3"):
    fname = f"raw_audio_{random.randint(100,999)}.{ext}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=60, stream=True, verify=False, allow_redirects=True)
        if r.status_code in [200, 206]:
            with open(fname, "wb") as f:
                for chunk in r.iter_content(8192): f.write(chunk)
            if is_valid_audio(fname): return fname
    except: pass
    try:
        os.system(f'curl -k -s -L -o "{fname}" "{url}"')
        if is_valid_audio(fname): return fname
    except: pass
    try: os.remove(fname)
    except: pass
    return None

def fetch_audio_dynamic():
    for f in glob.glob("raw_audio*") + ["temp_analysis.mp3", "final_audio.mp3", "thumb.jpg"]:
        try: os.remove(f)
        except: pass

    is_thursday = datetime.now().strftime("%A") == "Thursday"
    selected_surah_name = "الكهف" if is_thursday else random.choice(list(SURAHS_DICT.keys()))
    selected_reciter = random.choice(RECITERS)
    
    video_title = f"سورة {selected_surah_name}"
    downloaded_file = None

    search_query = f'"سورة {selected_surah_name}" بصوت "{selected_reciter}"'
    print(f"🔍 [المحرك 1] جاري البحث في SoundCloud عن: {search_query}")
    
    ydl_opts = {
        'format': 'bestaudio/best', 
        'outtmpl': 'raw_audio_sc.%(ext)s', 
        'quiet': True,
        'default_search': 'scsearch1',
        'nocheckcertificate': True
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl_dl: ydl_dl.download([search_query])
        files = glob.glob("raw_audio_sc.*")
        if files and is_valid_audio(files[0]):
            downloaded_file = files[0]
            print("✅ تم السحب من SoundCloud بنجاح!")
    except Exception as e: print(f"⚠️ تحذير: فشل SoundCloud: {e}")

    if not downloaded_file:
        print("🔄 تحويل مسار الهجوم إلى المحرك الديناميكي (MP3Quran API)...")
        backup_reciter = random.choice(["عبدالرحمن مسعد", "ياسر الدوسري"]) 
        surah_number = SURAHS_DICT[selected_surah_name]
        live_url = get_mp3quran_live_url(backup_reciter, surah_number)
        
        if live_url:
            print(f"🎯 تم توليد الرابط المباشر: {live_url}")
            downloaded_file = download_url_safe(live_url)
            if downloaded_file:
                selected_reciter = backup_reciter
                print("✅ تم السحب من سيرفرات MP3Quran بنجاح!")
        else: print("❌ لم يتم العثور على القارئ أو السورة.")

    if not downloaded_file: raise Exception("🚨 فشل كلا المحركين.")

    print("🧠 جاري تحليل الصوت وإجراء القص الذكي (Time-Jumping)...")
    full_audio = AudioFileClip(downloaded_file)
    max_start = max(0, full_audio.duration - 180.0) 
    start_time_for_clip = random.uniform(0.0, max_start)
    
    analysis_subclip = full_audio.subclip(start_time_for_clip, min(start_time_for_clip + 150.0, full_audio.duration))
    analysis_subclip.write_audiofile("temp_analysis.mp3", logger=None)
    
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe("temp_analysis.mp3", beam_size=5, word_timestamps=True)
    segments_list = list(segments)
    try: os.remove("temp_analysis.mp3")
    except: pass

    rel_start, rel_end, _ = get_smart_timestamps(segments_list, analysis_subclip.duration)
    
    if rel_start is None or rel_end is None:
        print("⚠️ فشل الذكاء الاصطناعي، تفعيل القص الآلي الدقيق بناءً على النص...")
        if segments_list:
            rel_start = segments_list[0].start
            rel_end = min(rel_start + 55.0, analysis_subclip.duration)
            best_gap = 0
            for i in range(len(segments_list) - 1):
                if segments_list[i].end > (rel_start + 45.0):
                    gap = segments_list[i+1].start - segments_list[i].end
                    if gap > 1.0 and gap > best_gap: 
                        best_gap = gap
                        rel_end = segments_list[i].end + (gap/2)
                        break
        else:
            rel_start, rel_end = 0.0, min(50.0, analysis_subclip.duration)

    # 🛡️ هامش أمان 2.5 ثانية لحماية نهاية الآية من التلاشي المبكر
    rel_end = min(rel_end + 2.5, analysis_subclip.duration)

    absolute_start = start_time_for_clip + rel_start
    absolute_end = start_time_for_clip + rel_end
        
    final_audio_duration = absolute_end - absolute_start
    trimmed_audio = full_audio.subclip(absolute_start, absolute_end)
    final_audio = trimmed_audio.audio_fadein(1.0).audio_fadeout(2.5) 
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    
    final_audio.close(); full_audio.close()
    try: os.remove(downloaded_file)
    except: pass
    
    return final_audio_duration, video_title, selected_reciter

def fetch_pexels_videos(target_duration):
    today = datetime.now().strftime("%A")
    query = "drone landscape, nature" if today in ['Sunday', 'Tuesday', 'Thursday'] else "clouds, peaceful nature"
    res_data = requests.get(f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&size=large&per_page=30&page={random.randint(1, 3)}", headers={"Authorization": PEXELS_API_KEY}).json()
    
    video_files, current_duration = [], 0
    for video in res_data['videos']:
        if any(t in str(video['tags']).lower() for t in ['people', 'woman', 'face']): continue
        vid_data = requests.get(video['video_files'][0]['link']).content
        vid_name = f"bg_{video['id']}.mp4"
        with open(vid_name, "wb") as f: f.write(vid_data)
        clip = VideoFileClip(vid_name)
        vertical_clip = crop_to_vertical(clip)
        video_files.append((vertical_clip, vid_name))
        current_duration += vertical_clip.duration
        if current_duration >= target_duration: break
    return video_files

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
    
    frame = video_with_audio.get_frame(2.0)
    img = Image.fromarray(frame)
    if img.mode != 'RGB': img = img.convert('RGB')
    img.save("thumb.jpg")
    
    video_with_audio.close(); final_video.close(); dark_overlay.close()
    for clip, name in clips_data:
        try: clip.close(); os.remove(name)
        except: pass

def publish_to_instagram(reciter_name, title):
    try:
        url_tg = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendVideo"
        with open('final_reel.mp4', 'rb') as video_file:
            requests.post(url_tg, data={'chat_id': ADMIN_CHAT_ID, 'caption': f"🎥 مقطع جاهز!\n\nالقارئ: {reciter_name}\nالسورة: {title}"}, files={'video': video_file}, timeout=200)
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
        cl.clip_upload("final_reel.mp4", caption, thumbnail="thumb.jpg")
        print("🎉 تم النشر بنجاح!")
    except Exception as e:
        raise Exception(f"❌ فشل النشر: {str(e)}")

if __name__ == "__main__":
    max_retries = 3 
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n🚀 محاولة {attempt}/{max_retries}...")
            dur, title, reciter = fetch_audio_dynamic()
            clips_data = fetch_pexels_videos(dur)
            render_cinematic_video(dur, clips_data)
            publish_to_instagram(reciter, title)
            send_telegram_alert("✅ تم النشر بنجاح والمشروع مستقر!")
            break 
        except Exception as e:
            if attempt < max_retries:
                send_telegram_alert(f"⚠️ فشل محاولة {attempt}. جاري الإعادة...\nالسبب: `{str(e)}`")
                time.sleep(10)
            else:
                send_telegram_alert(f"🚨 فشل نهائي!\nالسبب: `{str(e)}`")
                sys.exit(1)
