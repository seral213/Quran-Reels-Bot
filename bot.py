import os
import json
import time
import random
import requests
import traceback
import sys
import re
import glob
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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
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

# ================= 🧠 القص الذكي عبر الاتصال المباشر (REST API) =================
def get_smart_timestamps(transcript_segments):
    if not GEMINI_API_KEY:
        return None, None, "مفتاح GEMINI_API_KEY مفقود."

    full_text_with_time = ""
    for seg in transcript_segments:
        full_text_with_time += f"[{seg.start:.2f}s - {seg.end:.2f}s]: {seg.text}\n"

    prompt = f"""
    أنت خبير في القرآن الكريم. أمامك نص مستخرج من تلاوة قرآنية مع التوقيت الزمني لكل جملة.
    المطلوب تحديد نقطة البداية ونقطة النهاية بدقة (بالثواني) لعمل مقطع فيديو ريلز مدته بين 40 و 60 ثانية:
    1. البداية: ابحث عن أول كلمة يبدأ فيها القارئ التلاوة الفعلية (تخطى البسملة والاستعاذة والمقدمات).
    2. النهاية: ابحث عن نهاية آية صحيحة تكتمل بها المعاني.
    
    النص:
    {full_text_with_time}
    
    رد علي فقط بالأرقام بهذا الشكل بالضبط بدون أي نصوص إضافية:
    START: رقم
    END: رقم
    """
    
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }

    try:
        print("🔄 جاري الاتصال المباشر بعقل Gemini...")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            resp_data = response.json()
            text_response = resp_data['candidates'][0]['content']['parts'][0]['text']
            
            match_start = re.search(r'START:\s*([0-9.]+)', text_response)
            match_end = re.search(r'END:\s*([0-9.]+)', text_response)
            
            if match_start and match_end:
                start = float(match_start.group(1))
                end = float(match_end.group(1)) + 1.5 
                print("✅ نجح Gemini عبر الاتصال المباشر!")
                return start, end, None
            else:
                return None, None, "لم يتمكن Gemini من استخراج الأرقام بالصيغة المطلوبة."
        else:
            return None, None, f"خطأ في الاتصال المباشر: {response.status_code} - {response.text[:100]}"
    except Exception as e:
        return None, None, str(e)

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

# ================= بروتوكول السرب الشامل وجرد المخزون =================
def fetch_and_trim_audio():
    history = load_history()
    cookie_file = setup_cookies()
    
    ydl_opts_flat = {'quiet': True, 'extract_flat': True}
    if cookie_file: ydl_opts_flat['cookiefile'] = cookie_file
    
    forbidden_keywords = ['أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 'رقية', 'شرعية', 'دعاء', 'أدعية', 'بث مباشر']
    
    is_thursday = datetime.now().strftime("%A") == "Thursday"
    available_videos_pool = []
    
    print("جاري فحص مخزون الفيديوهات في القنوات...")
    with YoutubeDL(ydl_opts_flat) as ydl:
        for channel in CHANNELS:
            try:
                info = ydl.extract_info(channel['url'], download=False)
                entries_to_check = info.get('entries', [])
                
                if is_thursday:
                    kahf_entries = [e for e in entries_to_check if "الكهف" in e.get('title', '')]
                    if kahf_entries:
                        entries_to_check = kahf_entries

                for entry in entries_to_check:
                    vid_id = entry.get('id', '')
                    title = entry.get('title', '')
                    duration_sec = entry.get('duration', 0)
                    
                    if not vid_id or not title or duration_sec == 0: continue
                    if any(word.lower() in title.lower() for word in forbidden_keywords): continue
                    
                    saved_time = history['youtube_clips'].get(vid_id, 0.0)
                    if saved_time < (duration_sec - 60): 
                        available_videos_pool.append((entry, channel['name'], saved_time))
                        
            except Exception as e: print(f"خطأ أثناء فحص قناة {channel['name']}: {e}")

    remaining_count = len(available_videos_pool)
    if remaining_count == 0:
        raise Exception("❌ انتهت جميع الفيديوهات الصالحة في القنوات المحددة! يرجى إضافة قنوات جديدة أو مسح الذاكرة.")
    elif remaining_count <= 3:
        send_telegram_alert(f"🔔 *تنبيه قرب انتهاء المخزون!*\nمتبقي {remaining_count} فيديوهات صالحة فقط.")

    selected = random.choice(available_videos_pool)
    selected_video = selected[0]
    selected_reciter = selected[1]
    start_time_for_clip = selected[2]
    
    vid_id = selected_video['id']
    video_title = selected_video['title']
    video_url = f"https://www.youtube.com/watch?v={vid_id}"
    print(f"تم اختيار: {video_title}\nيبدأ القص من الدقيقة: {start_time_for_clip/60:.2f}")
    
    downloaded_file = None
    print("\n🚀 تفعيل بروتوكول السرب للتحميل...")
    
    for f in glob.glob("raw_audio.*") + ["temp_analysis.mp3", "final_audio.mp3"]:
        try: os.remove(f)
        except: pass
    
    # المحاولة 1: التخفي المحلي (بدون إجبار صيغة m4a لتجنب خطأ الفورمات)
    ydl_opts_dl = {
        'format': 'bestaudio/best', # تم التعديل لقبول أي صيغة صوت
        'outtmpl': 'raw_audio.%(ext)s', 
        'quiet': True,
        'extractor_args': {'youtube': ['player_client=android']}, # العودة للأندرويد لتجنب ألغاز JS
    }
    if cookie_file: ydl_opts_dl['cookiefile'] = cookie_file
    
    try:
        with YoutubeDL(ydl_opts_dl) as ydl_dl:
            ydl_dl.download([video_url])
        
        downloaded_files = glob.glob("raw_audio.*")
        if downloaded_files and is_valid_audio(downloaded_files[0]):
            downloaded_file = downloaded_files[0]
            print(f"🎉 تم التحميل محلياً بنجاح!")
        else:
            if downloaded_files: os.remove(downloaded_files[0])
    except Exception as e:
        error_msg = str(e).lower()
        print(f"❌ فشل المحلي: {error_msg}")

    # المحاولة 2: شبكة العناكب (Invidious API)
    if not downloaded_file:
        print("2️⃣ جاري محاولة التحميل عبر شبكة Invidious السرية...")
        invidious_instances = [
            "https://vid.puffyan.us", 
            "https://invidious.nerdvpn.de", 
            "https://inv.tux.pizza"
        ]
        random.shuffle(invidious_instances)
        
        for instance in invidious_instances:
            try:
                res = requests.get(f"{instance}/api/v1/videos/{vid_id}", timeout=15).json()
                formats = res.get("adaptiveFormats", [])
                
                audio_url = None
                for fmt in formats:
                    if 'audio' in fmt.get('type', ''):
                        audio_url = fmt.get('url')
                        break
                
                if audio_url:
                    audio_data = requests.get(audio_url, timeout=300).content
                    with open("raw_audio.webm", "wb") as f: f.write(audio_data)
                    
                    if is_valid_audio("raw_audio.webm"):
                        downloaded_file = "raw_audio.webm"
                        print(f"🎉 تم التحميل بنجاح عبر Invidious ({instance})!")
                        break
                    else:
                        os.remove("raw_audio.webm")
            except: continue

    # المحاولة 3: Cobalt הסحابي المحدث (إصدار V7 الجديد)
    if not downloaded_file:
        print("3️⃣ جاري تجربة Cobalt (الإصدار الجديد)...")
        try:
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            payload = {"url": video_url, "downloadMode": "audio", "audioFormat": "mp3"} # الهيكل الجديد
            res = requests.post("https://api.cobalt.tools/", json=payload, headers=headers, timeout=20)
            if res.status_code == 200 and res.json().get('url'):
                audio_data = requests.get(res.json().get('url'), timeout=300).content
                with open("raw_audio.mp3", "wb") as f: f.write(audio_data)
                if is_valid_audio("raw_audio.mp3"): 
                    downloaded_file = "raw_audio.mp3"
                    print("🎉 تم التحميل بنجاح عبر Cobalt!")
                else: os.remove("raw_audio.mp3")
        except: pass

    # المحاولة 4: شبكة Piped
    if not downloaded_file:
        print("4️⃣ جاري محاولة التحميل عبر شبكة Piped...")
        piped_instances = ["https://pipedapi.kavin.rocks", "https://pipedapi.tokhmi.xyz"]
        for instance in piped_instances:
            try:
                res = requests.get(f"{instance}/streams/{vid_id}", timeout=15).json()
                audio_streams = res.get("audioStreams", [])
                if audio_streams:
                    best_stream = audio_streams[-1]['url']
                    audio_data = requests.get(best_stream, timeout=300).content
                    with open("raw_audio.webm", "wb") as f: f.write(audio_data)
                    if is_valid_audio("raw_audio.webm"):
                        downloaded_file = "raw_audio.webm"
                        print("🎉 تم التحميل بنجاح عبر Piped!")
                        break
                    else: os.remove("raw_audio.webm")
            except: continue

    if not downloaded_file: 
        raise Exception("جميع أسلحة الاختراق (المحلي، Invidious، Cobalt، Piped) فشلت! يوتيوب مغلق تماماً اليوم.")

    print("🧠 جاري تحليل الصوت بالذكاء الاصطناعي...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    full_audio_clip = AudioFileClip(downloaded_file)
    analysis_end = min(start_time_for_clip + 150.0, full_audio_clip.duration)
    analysis_subclip = full_audio_clip.subclip(start_time_for_clip, analysis_end)
    analysis_subclip.write_audiofile("temp_analysis.mp3", logger=None)
    
    segments, info = model.transcribe("temp_analysis.mp3", beam_size=5, word_timestamps=True)
    segments_list = list(segments)
    try: os.remove("temp_analysis.mp3")
    except: pass

    # القص الذكي عبر الاتصال المباشر بـ Gemini
    rel_start, rel_end, gemini_error = get_smart_timestamps(segments_list)
    
    if rel_start is not None and rel_end is not None:
        absolute_start = start_time_for_clip + rel_start
        absolute_end = start_time_for_clip + rel_end
    else:
        send_telegram_alert(f"⚠️ *تنبيه:* نظام القص الذكي فشل، تم استخدام القص الآلي.\nالسبب: `{gemini_error}`")
        relative_start = 0.0
        if start_time_for_clip == 0.0:
            intro_keywords = ["بسم الله", "أعوذ بالله", "الحمد لله", "رب العالمين"]
            for segment in segments_list:
                if any(word in segment.text for word in intro_keywords) and segment.start < 60.0:
                    relative_start = segment.start; break
        relative_end = min(relative_start + 60.0, analysis_subclip.duration)
        best_gap = 0
        for i in range(len(segments_list) - 1):
            curr = segments_list[i]; nxt = segments_list[i+1]
            if curr.end > (relative_start + 45.0) and curr.end < relative_end:
                gap = nxt.start - curr.end
                if gap > 1.2 and gap > best_gap:
                    best_gap = gap; relative_end = curr.end + (gap / 2); break
        absolute_start = start_time_for_clip + relative_start
        absolute_end = start_time_for_clip + relative_end

    history['youtube_clips'][vid_id] = absolute_end
    final_audio_duration = absolute_end - absolute_start
    trimmed_audio = full_audio_clip.subclip(absolute_start, absolute_end)
    final_audio = trimmed_audio.audio_fadein(1.0).audio_fadeout(1.5)
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    
    final_audio.close(); full_audio_clip.close()
    try: os.remove(downloaded_file)
    except: pass
    
    return final_audio_duration, video_title, vid_id, selected_reciter, history

# ================= 3. جلب فيديوهات الطبيعة =================
def fetch_pexels_videos(target_duration, history):
    today = datetime.now().strftime("%A")
    query = "drone landscape, nature" if today in ['Sunday', 'Tuesday', 'Thursday'] else "clouds, peaceful nature"
    random_page = random.randint(1, 3)
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&size=large&per_page=30&page={random_page}"
    res_data = requests.get(url, headers=headers).json()
    
    video_files = []
    current_duration = 0
    for video in res_data['videos']:
        vid_id_str = str(video['id'])
        if vid_id_str in history['used_pexels']: continue
        if any(tag in str(video['tags']).lower() for tag in ['people', 'woman', 'face']): continue
        
        link = video['video_files'][0]['link']
        vid_data = requests.get(link).content
        vid_name = f"bg_vid_{vid_id_str}.mp4"
        with open(vid_name, "wb") as f: f.write(vid_data)
        clip = VideoFileClip(vid_name)
        video_files.append((clip, vid_name))
        current_duration += clip.duration
        history['used_pexels'].append(vid_id_str)
        if len(history['used_pexels']) > 60: history['used_pexels'].pop(0)
        if current_duration >= target_duration: break
    return video_files, history

# ================= 4. المونتاج السينمائي =================
def render_cinematic_video(audio_duration, clips_data):
    clips = [data[0] for data in clips_data]
    final_video = concatenate_videoclips(clips, method="compose", padding=-1).subclip(0, audio_duration)
    dark_overlay = ColorClip(size=final_video.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    box_width = int(final_video.w * 0.9)
    reshaped_main_title = fix_arabic("عافية قلب")
    txt_main = TextClip(reshaped_main_title, font="taj.ttf", fontsize=28, color='white', stroke_color='black', stroke_width=1, size=(box_width, None), method='caption', align='center')
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1.0)
    
    video_with_audio = CompositeVideoClip([final_video, dark_overlay, txt_main])
    video_with_audio = video_with_audio.fadein(1.0).fadeout(1.5)
    video_with_audio.audio = AudioFileClip("final_audio.mp3")
    video_with_audio.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac", threads=4)
    
    video_with_audio.close(); final_video.close(); dark_overlay.close()
    for clip, name in clips_data:
        try: os.remove(name)
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
                send_telegram_alert(f"⚠️ فشل محاولة {attempt}. انتظار 3 دقائق...\nالسبب: `{str(e)}`")
                time.sleep(180)
            else:
                send_telegram_alert(f"🚨 فشل نهائي!\nالسبب: `{str(e)}`")
                sys.exit(1)
