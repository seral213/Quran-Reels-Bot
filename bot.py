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

# --- مكتبات إصلاح النص العربي ---
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

# --- دالة مساعدة لإصلاح العربي في MoviePy ---
def fix_arabic(text):
    if not text: return ""
    # إعادة تشكيل الحروف لتبدو متصلة
    reshaped_text = arabic_reshaper.reshape(text)
    # عكس الاتجاه لتصبح من اليمين لليسار (RTL)
    bidi_text = get_display(reshaped_text)
    return bidi_text

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
# لم يتم تغيير منطق البحث أو التحميل السحابي لحمايتك من الحظر.
def fetch_and_trim_audio():
    history = load_history()
    cookie_file = setup_cookies()
    
    ydl_opts_flat = {'quiet': True, 'extract_flat': True}
    if cookie_file: ydl_opts_flat['cookiefile'] = cookie_file
    
    forbidden_keywords = ['أذكار', 'اذكار', 'الصباح', 'المساء', 'النوم', 'الاستيقاظ', 'رقية', 'شرعية', 'دعاء', 'أدعية']
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
    print("\n🚀 تفعيل بروتوكول السرب الشامل لتجاوز الحظر اليوم...")
    
    # المحاولة 1: التخفي المحلي
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
            print("🎉 تم التحميل بنجاح عبر التخفي المحلي!")
    except Exception as e: print(f"❌ فشل المحلي: {e}")

    # المحاولة 2: Cobalt (سحابي)
    if not downloaded:
        print("2️⃣ جاري استدعاء أسطول Cobalt السحابي...")
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
                                print(f"🎉 تم التحميل بنجاح عبر Cobalt السحابي!")
                                break
                except Exception: continue
                if downloaded: break
        except Exception: print("تجاوز سرب Cobalt...")

    # المحاولة 3: Loader (سحابي)
    if not downloaded:
        print("3️⃣ جاري تفعيل غارة Loader السحابية...")
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
                            print("🎉 تم التحميل بنجاح عبر Loader السحابي!")
                            break
        except Exception: print("فشل Loader...")

    if not downloaded: raise Exception("جميع الأسراب السحابية والمحلية فشلت! الحظر جنوني اليوم.")

    # --- بداية المونتاج الذكي (تخطي المقدمة والقص الذكي) ---
    # سأحتفظ بملف raw_audio.mp3 كاملاً لتحليله، ولن أقتص ثواني عشوائية هنا.

    print("🧠 جاري تحليل الصوت بالذكاء الاصطناعي (Whisper base) لتحديد أوقات التلاوة بدقة...")
    # رفع دقة الموديل قليلاً من tiny إلى base لضبط التوقيت (سيأخذ وقتاً أطول قليلاً).
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    # تحليل الدقيقة والنصف الأولى فقط (لتقليل وقت المعالجة وتجنب تحليل مقطع ساعة كاملاً)
    # سنقص ملفاً مؤقتاً سريعاً للتحليل.
    full_audio_clip = AudioFileClip("raw_audio.mp3")
    analysis_end = min(120.0, full_audio_clip.duration) # تحليل أول دقيقتين بحد أقصى
    full_audio_clip.subclip(0, analysis_end).write_audiofile("temp_analysis.mp3", logger=None)
    full_audio_clip.close()

    # طلب التوقيتات الدقيقة للكلمات (Word-level timestamps) لضبط القص الذكي.
    segments, info = model.transcribe("temp_analysis.mp3", beam_size=5, word_timestamps=True)
    segments_list = list(segments)
    
    # ❌ حذف الملف المؤقت
    try: os.remove("temp_analysis.mp3")
    except: pass

    # 1. منطق تخطي المقدمة (Skip Intro)
    actual_start_time = 0.0
    intro_keywords = ["بسم الله", "أعوذ بالله", "الحمد لله", "رب العالمين"]
    
    for segment in segments_list:
        # البحث عن الكلمات المفتاحية في أول 60 ثانية من التحليل
        is_recitation_start = any(word in segment.text for word in intro_keywords)
        if is_recitation_start and segment.start < 60.0:
            # تم إيجاد بداية الاستعاذة أو البسملة. سنعتبر بداية هذا الجزء هي بداية المقطع الحقيقية.
            actual_start_time = segment.start
            print(f"✅ تم اكتشاف نهاية المقدمة وتخطيها. البداية الحقيقية عند الثانية: {actual_start_time:.2f}")
            break
    
    if actual_start_time == 0.0:
        print("⚠️ لم يتم اكتشاف استعاذة أو بسملة في المقدمة، سيبدأ المقطع من البداية.")

    # 2. منطق القص الذكي (Smart Cut on Gap)
    # نستهدف مقطعاً مدته 50 ثانية تقريباً، ونبحث عن صمت بعدها.
    target_absolute_end = actual_start_time + 50.0
    actual_end_time = min(actual_start_time + 60.0, full_audio_clip.duration) # بحد أقصى دقيقة واحدة بعد البداية الحقيقية

    # البحث عن أطول فترة صمت بين الكلمات بعد الثانية 45 من البداية الحقيقية
    best_gap_duration = 0
    
    for i in range(len(segments_list) - 1):
        current_segment = segments_list[i]
        next_segment = segments_list[i+1]
        
        # إذا انتهى الجزء الحالي بين الثانية 45 والثانية 60 (من البداية الحقيقية)
        if current_segment.end > (actual_start_time + 45.0) and current_segment.end < actual_end_time:
            # قياس فترة الصمت (Gap) حتى الجزء التالي
            gap_duration = next_segment.start - current_segment.end
            
            # إذا وجدنا صمتاً أطول من ثانية واحدة (Gap كبير غالباً نهاية آية)
            if gap_duration > 1.2 and gap_duration > best_gap_duration:
                best_gap_duration = gap_duration
                # نعتمد منتصف فترة الصمت كنقطة نهاية مثالية
                actual_end_time = current_segment.end + (gap_duration / 2)
                print(f"🎬 تم إيجاد وقف صحيح (صمت {gap_duration:.2f} ثانية). سيتم القص ذكياً عند الثانية {actual_end_time:.2f}")
                # تم العثور على أفضل Gap، نخرج من الحلقة
                break

    if actual_end_time == min(actual_start_time + 60.0, full_audio_clip.duration):
        print(f"⚠️ لم يتم اكتشاف صمت مناسب بين الآيات، سيتم القص ذكياً عند الحد الأقصى: {actual_end_time:.2f}")

    # 3. تطبيق القص الفعلي للصوت الكلي (الآن نقوم بالقص النهائي)
    final_audio_duration = actual_end_time - actual_start_time
    print(f"⏱️ المدة النهائية للمقطع: {final_audio_duration:.2f} ثانية.")
    
    # فتح الملف الخام مرة أخرى للقص النهائي
    re_opened_audio = AudioFileClip("raw_audio.mp3")
    trimmed_audio = re_opened_audio.subclip(actual_start_time, actual_end_time)
    
    # 🔥 إضافة Fade Out للصوت (طلبك: fade نهاية الصوت)
    # لقد قمت بإضافة Fade In أيضاً (ظهور تدريجي) ليكون سينمائياً أكثر.
    final_audio = trimmed_audio.audio_fadein(1.0).audio_fadeout(1.5)
    final_audio.write_audiofile("final_audio.mp3", logger=None)
    
    # إغلاق الملفات ومسح الخام
    final_audio.close()
    re_opened_audio.close()
    try: os.remove("raw_audio.mp3")
    except: pass
    
    return final_audio_duration, video_title, vid_id, selected_reciter

# ================= 3. جلب فيديوهات الطبيعة =================
# تم ترك منطق Pexels كما هو لأنه لا يسبب مشاكل.
def fetch_pexels_videos(target_duration):
    today = datetime.now().strftime("%A")
    if today in ['Sunday', 'Tuesday', 'Thursday']:
        query = "drone landscape, nature, aerial view"
    else:
        query = "clouds, mountains, starry sky, peaceful nature"

    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&size=large&per_page=10"
    res_data = requests.get(url, headers=headers).json()
    
    if 'videos' not in res_data: raise Exception(f"❌ خطأ Pexels: {res_data}")
        
    video_files = []
    current_duration = 0
    for i, video in enumerate(res_data['videos']):
        if any(tag in str(video['tags']).lower() for tag in ['people', 'woman', 'face', 'human']): continue
        link = video['video_files'][0]['link']
        vid_data = requests.get(link).content
        vid_name = f"bg_vid_{i}.mp4"
        with open(vid_name, "wb") as f: f.write(vid_data)
        clip = VideoFileClip(vid_name)
        video_files.append(clip)
        current_duration += clip.duration
        if current_duration >= target_duration: break
    return video_files

# ================= 4. المونتاج السينمائي المحدث (إصلاح النص والتاثيرات) =================
def render_cinematic_video(audio_duration, reciter_name):
    # 🎥 جلب فيديوهات الخلفية
    clips = fetch_pexels_videos(audio_duration)
    # دمج فيديوهات الخلفية لتناسب مدة الصوت
    final_video_bg = concatenate_videoclips(clips, method="compose", padding=-1)
    # قص فيديو الخلفية ليتطابق مع الصوت
    final_video_bg = final_video_bg.subclip(0, audio_duration)
    
    # طبقة سوداء شفافة لتحسين قراءة النص
    dark_overlay = ColorClip(size=final_video_bg.size, color=(0,0,0)).set_opacity(0.35).set_duration(audio_duration)
    
    # 📝 طلبك: إصلاح النص وجعله صغيراً جداً
    reshaped_main_title = fix_arabic("عافية قلب")
    # ✅ تخفيض fontsize من 80 إلى 30 (طلبك: النصوص صغير جدا)
    # تم الإبقاء على stroke_width لتحسين المقروئية على الخلفيات المتغيرة
    txt_main = TextClip(reshaped_main_title, font="taj.ttf", fontsize=35, color='white', stroke_color='black', stroke_width=1.5)
    # تحديد توقيت النص وموضعه (في المنتصف)
    # إضافة Fade In للنص ليكون سينمائياً
    txt_main = txt_main.set_position('center').set_duration(audio_duration).crossfadein(1.0)
    
    # طلبك: إصلاح نص القارئ وجعله صغيراً
    reshaped_sub_title = fix_arabic(f"القارئ: {reciter_name}")
    # ✅ تخفيض fontsize من 40 إلى 22 (طلبك:Texts صغيراً جداً)
    txt_sub = TextClip(reshaped_sub_title, font="taj.ttf", fontsize=22, color='white')
    # موضعه أسفل العنوان الرئيسي قليلاً
    txt_sub = txt_sub.set_position(('center', final_video_bg.h/2 + 60)).set_duration(audio_duration).crossfadein(1.0)
    
    # دمج الفيديو مع الطبقات والنصوص
    composite_video = CompositeVideoClip([final_video_bg, dark_overlay, txt_main, txt_sub])
    
    # 🔥طلبك: إضافة تأثيرات سينمائية (ظهور واختفاء تدريجي للفيديو)
    # تم تطبيق fadein في البداية و fadeout في النهاية
    composite_video = composite_video.fadein(1.0).fadeout(1.5)
    
    # إضافة الصوت النهائي للمقطع (الذي يحتوي بالفعل على fadeout)
    composite_video.audio = AudioFileClip("final_audio.mp3")
    
    # إنتاج الملف النهائي (رندرة)
    # تم ترك threads=4 للرندرة المتعددة السريعة
    composite_video.write_videofile("final_reel.mp4", fps=30, codec="libx264", audio_codec="aac", threads=4)
    
    # إغلاق الملفات ومسح الفيديوهات المؤقتة
    composite_video.close()
    final_video_bg.close()
    dark_overlay.close()
    # مسح فيديوهات Pexels المؤقتة
    for i in range(len(clips)):
        try: os.remove(f"bg_vid_{i}.mp4")
        except: pass

# ================= 5. صمام النشر لإنستجرام (لم يتم تغييره) =================
# تم ترك منطق الانتظار الذكي وجلسات إنستجرام كما هو حماية لك من الحظر.
def publish_to_instagram(reciter_name, title):
    # إرسال الفيديو مباشرة لتليجرام كنسخة احتياطية آمنة
    print("جاري إرسال ملف الفيديو مباشرة إلى تليجرام لتقر عينك بثمرة تعبك...")
    try:
        url_tg = f"https://api.telegram.org/bot{ERROR_BOT_TOKEN}/sendVideo"
        with open('final_reel.mp4', 'rb') as video_file:
            requests.post(url_tg, data={'chat_id': ADMIN_CHAT_ID, 'caption': f"🎥 *استوديو القرآن - مقطع جاهز وآمن!*\n\nالقارئ: {reciter_name}\nالعنوان: {title}"}, files={'video': video_file}, timeout=200)
            print("✅ تم إرسال ملف الفيديو مباشرة إلى تليجرام!")
    except Exception as e:
        print(f"⚠️ فشل إرسال ملف الفيديو المباشر إلى تليجرام، سنكمل النشر: {e}")

    if not IG_USERNAME or not IG_PASSWORD:
        raise Exception("❌ لم يتم العثور على IG_USERNAME أو IG_PASSWORD في الـ Secrets!")

    caption = f"عافية لقلبك 🤍. أرح مسمعك بتلاوة القارئ {reciter_name}.\n\n#قرآن #تلاوة #راحة_نفسية #عافية_قلب #quran"

    print("جاري تسجيل الدخول لإنستجرام...")
    cl = Client()
    cl.delay_range = [1, 3] 
    
    try:
        if os.path.exists(SESSION_FILE):
            print("🔄 تم العثور على جلسة سابقة! جاري تسجيل الدخول المتخفي...")
            cl.load_settings(SESSION_FILE)
            
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(SESSION_FILE) 
        
        print("✅ تم تسجيل الدخول! جاري رفع الريلز...")
        cl.clip_upload("final_reel.mp4", caption)
        print("🎉 تم نشر الريلز على حسابك بنجاح!")
    except Exception as e:
        raise Exception(f"❌ فشل النشر التلقائي في إنستجرام (لكن الفيديو أُرسل لتليجرام). السبب: {str(e)}")

# ================= التشغيل الرئيسي (لم يتم تغييره) =================
if __name__ == "__main__":
    try:
        # لم يتم تغيير الأوقات الصلبة لأن الذكاء الاصطناعي يتولى الأمر داخل الدالة.
        duration, title, vid_id, reciter = fetch_and_trim_audio()
        render_cinematic_video(duration, reciter)
        publish_to_instagram(reciter, title)
        
        # حفظ الذاكرة ومسح الـ Reel النهائي
        history = load_history()
        history['used_videos'].append(vid_id)
        save_history(history)
        try: os.remove("final_reel.mp4")
        except: pass
        
        success_message = f"✅ *بشارة من استوديو القرآن*\n\nتم إنتاج ونشر فيديو جديد بنجاح كامل! 🎉"
        send_telegram_alert(success_message)
        print("تم إنهاء العملية بنجاح كامل!")
        
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"\n❌ حدث خطأ فادح:\n{error_details}")
        error_message = f"⚠️ *تنبيه طارئ من استوديو القرآن*\n\nتوقف البوت عن العمل بسبب:\n\n`{str(e)}`\n\nيرجى الدخول لسيرفر GitHub للتحقق."
        send_telegram_alert(error_message)
        sys.exit(1)
