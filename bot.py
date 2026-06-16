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
COHERE_API_KEY = os.environ.get("COHERE_API_KEY") 
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

def send_telegram_photo(photo_path, caption=""):
    """دالة مستقلة ومحصنة لإرسال الصور (كاميرا التجسس)"""
    if not ERROR_BOT_TOKEN or not ADMIN_CHAT_ID or not os.path.exists(photo_path): return
    url = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            requests.post(url, data={'chat_id': ADMIN_CHAT_ID, 'caption': caption}, files={'photo': photo}, timeout=30)
    except Exception as e: print(f"فشل إرسال الصورة لتليجرام: {e}")

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

# ================= 🧠 العقول المجانية (قص دقيق للآيات وإجبار للوقت) =================
def get_smart_timestamps(transcript_segments, max_duration):
    if not transcript_segments: return None, None

    numbered_text = ""
    for index, seg in enumerate(transcript_segments):
        numbered_text += f"السطر [{index}]: {seg.text} (الوقت: {seg.start:.0f} ثانية)\n"

    # 🌟 التوجيه الصارم: آيات دقيقة + وقت محدد
    prompt = f"""أنت مخرج فيديو قرآني محترف.
مهمتك اختيار بداية ونهاية لمقطع فيديو (ريلز). الأسطر التالية مقطعة بناءً على نَفَس القارئ.

شروطك الصارمة جداً:
1. السطر الأول يجب أن يكون بداية آية جديدة (ليس تكملة آية سابقة).
2. السطر الأخير يجب أن يكون نهاية آية (يقف القارئ وتكتمل المعاني).
3. القاعدة الذهبية: فرق الوقت بين البداية والنهاية يجب أن يكون بين 30 ثانية و 45 ثانية فقط! (يُمنع تجاوز 48 ثانية نهائياً).

النص:
{numbered_text}

أجب فقط برقمي السطرين بصيغة مصفوفة:
[البداية, النهاية]
"""
    
    start_time = None
    end_time = None

    def enforce_time_rule(start_idx, end_idx):
        """القفل الإجباري: يضمن أن الوقت مستحيل يتجاوز 50 ثانية وأن البداية/النهاية دقيقة"""
        nonlocal start_time, end_time
        s_time = transcript_segments[start_idx].start
        e_time = transcript_segments[end_idx].end
        
        # إذا كان الذكاء الاصطناعي غبياً وتجاوز 48 ثانية، بايثون سيصلح الخطأ
        while (e_time - s_time) > 48.0 and end_idx > start_idx:
            end_idx -= 1
            e_time = transcript_segments[end_idx].end
            
        return s_time, e_time

    if COHERE_API_KEY:
        try:
            print("🧠 جاري محاولة القص عبر القائد (Cohere - Command-R)...")
            api_url = "https://api.cohere.com/v1/chat"
            headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
            payload = {"message": prompt, "model": "command-r", "temperature": 0.0}
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                text_response = response.json().get('text', '')
                match = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*\]', text_response)
                if match:
                    start_idx, end_idx = int(match.group(1)), int(match.group(2))
                    if start_idx < len(transcript_segments) and end_idx < len(transcript_segments):
                        start_time, end_time = enforce_time_rule(start_idx, end_idx)
                        return start_time, end_time
        except Exception as e: print(f"⚠️ خطأ في Cohere: {e}")

    if GROQ_API_KEY and not start_time:
        try:
            print("🔄 تفعيل المحرك الاحتياطي (Groq)...")
            groq_url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0}
            response = requests.post(groq_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                text_response = response.json()['choices'][0]['message']['content']
                match = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*\]', text_response)
                if match:
                    start_idx, end_idx = int(match.group(1)), int(match.group(2))
                    if start_idx < len(transcript_segments) and end_idx < len(transcript_segments):
                        start_time, end_time = enforce_time_rule(start_idx, end_idx)
                        return start_time, end_time
        except Exception as e: print(f"❌ خطأ في Groq: {e}")

    return None, None

def fix_arabic(text):
    if not text: return ""
    reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})
    return get_display(reshaper.reshape(f" {text} "))

def get_mp3quran_live_url(reciter_name, surah_number):
    print("📡 جاري الاتصال بقاعدة بيانات MP3Quran...")
    api_url = "https://mp3quran.net/api/v3/reciters?language=ar"
    try:
        res = requests.get(api_url, timeout=15, verify=False).json()
        for reciter in res.get('reciters', []):
            if reciter_name in reciter.get('name', ''):
                for moshaf in reciter.get('moshaf', []):
                    server_url = moshaf.get('server', '')
                    if server_url:
                        if not server_url.endswith('/'): server_url += '/'
                        return f"{server_url}{surah_number:03d}.mp3"
    except: pass
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
    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': 'raw_audio_sc.%(ext)s', 'quiet': True, 'default_search': 'scsearch1', 'nocheckcertificate': True}
    
    try:
        with YoutubeDL(ydl_opts) as ydl_dl: ydl_dl.download([search_query])
        files = glob.glob("raw_audio_sc.*")
        if files and is_valid_audio(files[0]):
            downloaded_file = files[0]
    except: pass

    if not downloaded_file:
        backup_reciter = random.choice(["عبدالرحمن مسعد", "ياسر الدوسري"]) 
        live_url = get_mp3quran_live_url(backup_reciter, SURAHS_DICT[selected_surah_name])
        if live_url:
            downloaded_file = download_url_safe(live_url)
            if downloaded_file: selected_reciter = backup_reciter

    if not downloaded_file: raise Exception("🚨 فشل كلا المحركين.")

    full_audio = AudioFileClip(downloaded_file)
    max_start = max(0, full_audio.duration - 180.0) 
    start_time_for_clip = random.uniform(0.0, max_start)
    
    analysis_subclip = full_audio.subclip(start_time_for_clip, min(start_time_for_clip + 150.0, full_audio.duration))
    analysis_subclip.write_audiofile("temp_analysis.mp3", logger=None)
    
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segments, _ = model.transcribe("temp_analysis.mp3", beam_size=5, word_timestamps=True, initial_prompt="بسم الله الرحمن الرحيم. تلاوة قرآن.")
    segments_list = list(segments)
    try: os.remove("temp_analysis.mp3")
    except: pass

    clean_segments = []
    for seg in segments_list:
        text_clean = seg.text.replace(" ", "") 
        if "بسمالله" in text_clean or "صدقالله" in text_clean:
            if len(clean_segments) < 10: 
                clean_segments = []
                continue
            else: break
        clean_segments.append(seg)
    if len(clean_segments) >= 8: segments_list = clean_segments

    rel_start, rel_end = get_smart_timestamps(segments_list, analysis_subclip.duration)
    
    if rel_start is None or rel_end is None:
        if segments_list:
            rel_start = segments_list[0].start
            # الإجباري: 40 ثانية كحد أقصى للقص اليدوي
            rel_end = min(rel_start + 40.0, analysis_subclip.duration)
        else:
            rel_start, rel_end = 0.0, min(40.0, analysis_subclip.duration)

    absolute_start = start_time_for_clip + rel_start
    absolute_end = start_time_for_clip + rel_end
        
    final_audio_duration = absolute_end - absolute_start
    trimmed_audio = full_audio.subclip(absolute_start, absolute_end)
    
    # تلاشي بسيط جداً (0.4) حتى لا يأكل الحرف الأخير
    final_audio = trimmed_audio.audio_fadein(0.1).audio_fadeout(0.4) 
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
    
    txt_base = TextClip(fix_arabic("عافية قلب"), font="taj.ttf", fontsize=45, color='white', stroke_color='black', stroke_width=2, method='caption', size=(900, None), align='center').set_position('center')
    
    t1 = txt_base.set_start(0.0).set_duration(0.15)
    t2 = txt_base.set_start(0.25).set_duration(0.1)
    t3 = txt_base.set_start(0.5).set_duration(0.15)
    t4 = txt_base.set_start(0.8).set_duration(audio_duration - 0.8) 
    
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, t1, t2, t3, t4], size=(1080, 1920))
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


def publish_to_youtube(video_path, reciter_name, title):
    yt_cookies_str = os.environ.get("YT_COOKIES")
    if not yt_cookies_str:
        print("⚠️ لم يتم العثور على YT_COOKIES، سيتم تخطي النشر في يوتيوب.")
        return

    print("🚀 جاري النشر على يوتيوب شورتس عبر المتصفح الوهمي...")
    page = None 
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            context.set_default_timeout(60000) 
            
            # 🌟 تنظيف وحقن الكوكيز بصيغة JSON الاحترافية 🌟
            raw_cookies = json.loads(yt_cookies_str)
            cleaned_cookies = []
            for c in raw_cookies:
                clean_c = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c["path"]
                }
                if "secure" in c: clean_c["secure"] = c["secure"]
                if "httpOnly" in c: clean_c["httpOnly"] = c["httpOnly"]
                if "sameSite" in c:
                    ss = c["sameSite"].lower()
                    if ss in ["no_restriction", "unspecified", "none"]: clean_c["sameSite"] = "None"
                    elif ss == "lax": clean_c["sameSite"] = "Lax"
                    elif ss == "strict": clean_c["sameSite"] = "Strict"
                cleaned_cookies.append(clean_c)
                
            context.add_cookies(cleaned_cookies)
            
            page = context.new_page()
            page.goto("https://studio.youtube.com/?hl=en", timeout=90000)
            page.wait_for_load_state("networkidle")
            
            print("✅ جاري البحث عن زر الرفع...")
            page.wait_for_selector("#create-icon", state="visible")
            page.locator("#create-icon").click()
            
            page.wait_for_selector("tp-yt-paper-item", state="visible")
            page.locator("tp-yt-paper-item").first.click()
            
            page.wait_for_selector("input[type='file']", state="attached")
            page.locator("input[type='file']").set_input_files(video_path)
            
            print("⏳ جاري تعبئة البيانات...")
            page.wait_for_selector("#title-textarea #textbox", state="visible", timeout=60000)
            
            page.locator("#title-textarea #textbox").fill(f"تلاوة عذبة تريح القلب - {reciter_name} 🤍 #shorts")
            page.locator("#description-textarea #textbox").fill(f"أرح مسمعك وعافية لقلبك بتلاوة القارئ {reciter_name}\n\n#قرآن #تلاوة #shorts")
            page.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']").click()
            
            for _ in range(3):
                page.locator("#next-button").click()
                page.wait_for_timeout(2000) 
            
            page.wait_for_selector("tp-yt-paper-radio-button[name='PUBLIC']", state="visible")
            page.locator("tp-yt-paper-radio-button[name='PUBLIC']").click()
            
            page.locator("#done-button").click()
            page.wait_for_selector("ytcp-button#close-button", timeout=120000)
            
            print("🎉 تم نشر الشورتس على يوتيوب بنجاح!")
            browser.close()
            send_telegram_alert(f"✅ تم النشر في يوتيوب شورتس بنجاح!\nالقارئ: {reciter_name}")

    except Exception as e:
        print(f"❌ فشل يوتيوب: {e}")
        if page:
            try:
                page.screenshot(path="yt_error.png")
                send_telegram_photo("yt_error.png", f"⚠️ فشل يوتيوب. تم التقاط هذه الصورة من السيرفر:\n{str(e)[:100]}")
            except Exception as pic_err:
                send_telegram_alert(f"⚠️ فشل يوتيوب وفشلت كاميرا التجسس!\nالخطأ: {str(e)[:100]}")

def publish_to_instagram(reciter_name, title):
    try:
        url_tg = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendVideo"
        with open('final_reel.mp4', 'rb') as video_file:
            requests.post(url_tg, data={'chat_id': ADMIN_CHAT_ID, 'caption': f"🎥 مقطع جاهز!\n\nالقارئ: {reciter_name}\nالسورة: {title}"}, files={'video': video_file})
    except: pass

    is_thursday = datetime.now().strftime("%A") == "Thursday"
    caption = f"✨ نور ما بين الجمعتين.\n\nالقارئ: {reciter_name} 🤍\n#يوم_الجمعة #قرآن #عافية_قلب #تلاوة" if is_thursday else f"عافية لقلبك 🤍.\nالقارئ: {reciter_name}.\n\n#قرآن #تلاوة #عافية_قلب #راحة"
    
    cl = Client()
    if os.path.exists(SESSION_FILE): cl.load_settings(SESSION_FILE)
    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(SESSION_FILE)
        cl.clip_upload("final_reel.mp4", caption, thumbnail="thumb.jpg")
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
            
            try: publish_to_youtube("final_reel.mp4", reciter, title)
            except Exception as yt_err: print(f"خطأ يوتيوب غير متوقع: {yt_err}")

            publish_to_instagram(reciter, title)
            send_telegram_alert("✅ تم إنجاز المهمة بنجاح والمشروع مستقر!")
            break 
            
        except Exception as e:
            if attempt < max_retries:
                send_telegram_alert(f"⚠️ فشل محاولة {attempt}...\n`{str(e)[:100]}`")
                time.sleep(10)
            else:
                send_telegram_alert(f"🚨 فشل نهائي!\n`{str(e)[:100]}`")
                sys.exit(1)
