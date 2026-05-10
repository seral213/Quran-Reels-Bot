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

# إخفاء تحذيرات الأمان المزعجة في السجل
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
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
RAPID_API_KEY = os.environ.get("RAPID_API_KEY")
HISTORY_FILE = "history.json"
SESSION_FILE = "session.json"

# ================= نظام إشعارات تليجرام =================
def send_telegram_alert(message):
    if not ERROR_BOT_TOKEN or not ADMIN_CHAT_ID: return
    url = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, data=payload)
    except Exception: pass

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

# ================= 🧠 القص الذكي =================
def get_smart_timestamps(transcript_segments):
    if not GEMINI_API_KEY: return None, None, "مفتاح مفقود."
    full_text_with_time = "".join([f"[{seg.start:.2f}s - {seg.end:.2f}s]: {seg.text}\n" for seg in transcript_segments])

    prompt = f"""
    أنت خبير في القرآن. أمامك نص مستخرج من تلاوة.
    حدد البداية والنهاية (بالثواني) لعمل مقطع بين 40 و 58 ثانية:
    1. البداية: ابدأ مع أول كلمة فعلية للتلاوة.
    2. النهاية: يجب أن تكون عند نهاية آية تامة المعنى.
    
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

# ================= القنوات وخطة الطوارئ =================
CHANNELS = [
    {"url": "https://www.youtube.com/@abdullahshaab1/videos", "name": "عبدالله شعبان"},
    {"url": "https://www.youtube.com/@9li9/videos", "name": "عبدالرحمن مسعد"}
]

# السيرفر 11 معروف باستقراره الدائم لقرآن MP3
EMERGENCY_LINKS = [
    {"url": "https://server11.mp3quran.net/mosaad/018.mp3", "title": "سورة الكهف", "reciter": "عبدالرحمن مسعد"},
    {"url": "https://server11.mp3quran.net/mosaad/067.mp3", "title": "سورة الملك", "reciter": "عبدالرحمن مسعد"},
    {"url": "https://server11.mp3quran.net/mosaad/055.mp3", "title": "سورة الرحمن", "reciter": "عبدالرحمن مسعد"}
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f: return json.load(f)
        except: pass
    return {"youtube_clips": {}, "used_pexels": []}

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

# ================= 🛡️ دبابة التحميل الصارمة (تكتيك التخييم) =================
def download_url_safe(url, ext="mp3"):
    print(f"🔗 جاري بدء عملية السحب من الرابط المباشر...")
    if url.startswith("//"): url = "https:" + url 
    fname = f"raw_audio_{random.randint(100,999)}.{ext}"

    # هوية متصفح كاملة لعدم إثارة شكوك الكلاودفلير
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5",
        "Connection": "keep-alive"
    }

    # 🔄 التكتيك الجديد: تكرار المحاولة 5 مرات، بانتظار 5 ثواني بينها (لانتظار تجهيز الملف في السيرفر)
    for attempt in range(1, 6):
        print(f"⏳ محاولة السحب ({attempt}/5)...")
        try:
            r = requests.get(url, headers=headers, timeout=60, stream=True, verify=False, allow_redirects=True)
            if r.status_code in [200, 206]:
                with open(fname, "wb") as f:
                    for chunk in r.iter_content(8192): f.write(chunk)
                if is_valid_audio(fname): 
                    print("✅ تم سحب الملف المباشر بنجاح!")
                    return fname
            else:
                print(f"⚠️ السيرفر رد بالكود {r.status_code} (الملف غير جاهز بعد أو محمي).")
        except Exception as e:
            print(f"⚠️ خطأ أثناء محاولة السحب: {e}")
        
        # ننام 5 ثواني ثم نهجم مرة أخرى
        time.sleep(5)

    # 💥 الضربة الأخيرة بأداة curl إذا فشلت requests
    print("🔄 جاري تجربة السحب العنيف عبر curl...")
    try:
        os.system(f'curl -k -s -L -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -o "{fname}" "{url}"')
        if is_valid_audio(fname): 
            print("✅ نجح السحب العنيف!")
            return fname
    except: pass

    try: os.remove(fname)
    except: pass
    return None

# ================= بروتوكول التشغيل الرئيسي =================
def fetch_and_trim_audio():
    history = load_history()
    ydl_opts_flat = {'quiet': True, 'extract_flat': True}
    
    forbidden_keywords = ['أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 'رقية', 'شرعية', 'دعاء', 'أدعية', 'بث مباشر']
    is_thursday = datetime.now().strftime("%A") == "Thursday"
    available_videos_pool = []
    
    print("جاري فحص مخزون الفيديوهات...")
    with YoutubeDL(ydl_opts_flat) as ydl:
        for channel in CHANNELS:
            try:
                info = ydl.extract_info(channel['url'], download=False)
                entries = info.get('entries', [])
                if is_thursday: entries = [e for e in entries if "الكهف" in e.get('title', '')] or entries

                for entry in entries:
                    vid_id = entry.get('id', '')
                    title = entry.get('title', '')
                    duration = entry.get('duration', 0)
                    if not vid_id or not title or duration == 0: continue
                    if any(w in title.lower() for w in forbidden_keywords): continue
                    if history['youtube_clips'].get(vid_id, 0.0) < (duration - 60): 
                        available_videos_pool.append((entry, channel['name']))
            except: pass

    if not available_videos_pool: raise Exception("❌ انتهت الفيديوهات الصالحة!")

    selected = random.choice(available_videos_pool)
    vid_id = selected[0]['id']
    video_title = selected[0]['title']
    selected_reciter = selected[1]
    
    for f in glob.glob("raw_audio*") + ["temp_analysis.mp3", "final_audio.mp3"]:
        try: os.remove(f)
        except: pass

    downloaded_file = None

    # ================= 🚀 RapidAPI (الأداة القديمة المضمونة ytjar) =================
    if RAPID_API_KEY and not downloaded_file:
        print("1️⃣ جاري التحميل عبر أداة RapidAPI (ytjar)...")
        url = "https://youtube-mp36.p.rapidapi.com/dl"
        headers = {"x-rapidapi-key": RAPID_API_KEY, "x-rapidapi-host": "youtube-mp36.p.rapidapi.com"}
        
        for i in range(8):
            try:
                res = requests.get(url, headers=headers, params={"id": vid_id}, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    status = data.get("status")
                    if status == "ok" and data.get("link"):
                        print("🎉 تم تحويل المقطع بنجاح في سيرفراتهم!")
                        # الانتظار الأول قبل السحب
                        time.sleep(3)
                        downloaded_file = download_url_safe(data["link"])
                        break
                    elif status == "processing":
                        print(f"⏳ المقطع قيد المعالجة (محاولة {i+1}/8)...")
                        time.sleep(4)
                elif res.status_code == 403:
                    print("❌ الأداة تحتاج اشتراك، سيتم الانتقال للبديل.")
                    break
                else: break
            except: break

    # ================= 🌐 شبكة Invidious العالمية كبديل =================
    if not downloaded_file:
        print("2️⃣ جاري محاولة السحب عبر شبكة Invidious اللامركزية...")
        invidious_instances = ["https://inv.tux.pizza", "https://vid.puffyan.us", "https://invidious.flokinet.to"]
        random.shuffle(invidious_instances)
        
        for instance in invidious_instances:
            try:
                res = requests.get(f"{instance}/api/v1/videos/{vid_id}", timeout=10).json()
                for fmt in res.get("adaptiveFormats", []):
                    if "audio" in fmt.get("type", ""):
                        print(f"🎉 تم العثور على رابط عبر {instance}!")
                        downloaded_file = download_url_safe(fmt["url"], ext="m4a")
                        if downloaded_file: break
                if downloaded_file: break
            except: continue

    # ================= 🛡️ خطة الطوارئ القصوى =================
    if not downloaded_file:
        print("⚠️ فشل يوتيوب تماماً! تفعيل خطة الطوارئ البديلة المحدثة...")
        emergency = random.choice(EMERGENCY_LINKS)
        downloaded_file = download_url_safe(emergency["url"])
        if downloaded_file:
            video_title, vid_id, selected_reciter = emergency["title"] + " (طوارئ)", "EMERGENCY_" + str(random.randint(1000, 9999)), emergency["reciter"]
            start_time_for_clip = random.uniform(0.0, 180.0)
        else: raise Exception("فشلت جميع خطوط الهجوم وخطة الطوارئ أيضاً.")

    print("🧠 جاري تحليل الصوت وإجراء القص الذكي...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    full_audio = AudioFileClip(downloaded_file)
    analysis_subclip = full_audio.subclip(start_time_for_clip, min(start_time_for_clip + 150.0, full_audio.duration))
    analysis_subclip.write_audiofile("temp_analysis.mp3", logger=None)
    
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

    if not str(vid_id).startswith("EMERGENCY_"): history['youtube_clips'][vid_id] = absolute_end
        
    final_audio_duration = absolute_end - absolute_start
    trimmed_audio = full_audio.subclip(absolute_start, absolute_end)
    final_audio = trimmed_audio.audio_fadein(1.0).audio_fadeout(2.5) 
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    
    final_audio.close(); full_audio.close()
    try: os.remove(downloaded_file)
    except: pass
    
    return final_audio_duration, video_title, vid_id, selected_reciter, history

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
        caption = f"✨ سورة الكهف نور ما بين الجمعتين. لا تنسوا السنن والصلاة على النبي ﷺ.\n\nتلاوة القارئ: {reciter_name} 🤍\n#سورة_الكهف #يوم_الجمعة #قرآن #عافية_قلب"
    else:
        caption = f"عافية لقلبك 🤍. أرح مسمعك بتلاوة القارئ {reciter_name}.\n\n#قرآن #تلاوة #عافية_قلب"
    
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
    max_retries = 3 
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n🚀 محاولة {attempt}/{max_retries}...")
            dur, title, vid_id, reciter, history = fetch_and_trim_audio()
            clips_data, updated_history = fetch_pexels_videos(dur, history)
            render_cinematic_video(dur, clips_data)
            publish_to_instagram(reciter, title)
            save_history(updated_history)
            send_telegram_alert("✅ تم النشر بنجاح!")
            break 
        except Exception as e:
            if attempt < max_retries:
                send_telegram_alert(f"⚠️ فشل محاولة {attempt}. جاري إعادة المحاولة...\nالسبب: `{str(e)}`")
                time.sleep(10)
            else:
                send_telegram_alert(f"🚨 فشل نهائي بعد 3 محاولات!\nالسبب: `{str(e)}`")
                sys.exit(1)
