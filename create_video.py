import os
import subprocess
import re
import math
import shutil

# =================================================================
#                 কনফিগারেশন (Configuration)
# =================================================================
CONVERT_IMAGES = True 
TARGET_RESOLUTION = '1920x1080'
TARGET_EXTENSION = 'jpg'
CONVERTED_DIR = 'converted_images'

SRT_FILE = '' 
AUDIO_FILE = ''
OUTPUT_FILE = ''

# [CHANGE] বাফার এখন ০.০ সেকেন্ড। ভিডিও এবং অডিও একদম সমান হবে।
BUFFER_SECONDS = 0.0 

SUPPORTED_IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff']
SUPPORTED_AUDIO_EXTENSIONS = ['mp3', 'wav', 'aac', 'm4a', 'ogg', 'flac']
# =================================================================

def get_image_numbers_from_srt():
    try:
        with open(SRT_FILE, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        numbers = []
        for i, line in enumerate(lines):
            line = line.strip()
            if line.isdigit():
                try:
                    next_line = lines[i + 1]
                    if '-->' in next_line:
                        numbers.append(line)
                except IndexError:
                    continue
        return numbers
    except FileNotFoundError:
        return []

def preprocess_images():
    if not CONVERT_IMAGES: return True
    print(f"\n[INFO] ইমেজ প্রসেসিং... ({TARGET_RESOLUTION})")
    if not os.path.exists(CONVERTED_DIR): os.makedirs(CONVERTED_DIR)

    image_numbers = get_image_numbers_from_srt()
    if not image_numbers: return False

    try:
        target_w, target_h = TARGET_RESOLUTION.split('x')
    except ValueError: return False

    total_images = len(image_numbers)
    for i, number in enumerate(image_numbers):
        original = find_original_image_file(number)
        if not original: continue
        
        converted = os.path.join(CONVERTED_DIR, f"{number}.{TARGET_EXTENSION}")
        if os.path.exists(converted): continue

        vf = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black"
        try:
            subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', original, '-vf', vf, converted], check=True)
            print(f"Processed ({i+1}/{total_images}): {number}", end='\r')
        except subprocess.CalledProcessError: return False
    print("\n[SUCCESS] প্রসেসিং সম্পন্ন।")
    return True

def find_original_image_file(number):
    for ext in SUPPORTED_IMAGE_EXTENSIONS:
        f = f"{number}.{ext}"
        if os.path.exists(f): return f
    return None

def find_image_file(number):
    if CONVERT_IMAGES:
        c = os.path.join(CONVERTED_DIR, f"{number}.{TARGET_EXTENSION}")
        if os.path.exists(c): return c
    return find_original_image_file(number)

def get_audio_duration(audio_file_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_file_path]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        return float(res.stdout.strip())
    except Exception: return None

def time_str_to_seconds(time_str):
    try:
        h, m, s_ms = time_str.split(':'); s, ms = s_ms.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    except ValueError: return 0

def setup_and_adjust_files():
    global SRT_FILE, AUDIO_FILE, OUTPUT_FILE
    for f in os.listdir('.'):
        if not SRT_FILE and f.lower().endswith('.srt'): SRT_FILE = f
        if not AUDIO_FILE and any(f.lower().endswith(f".{e}") for e in SUPPORTED_AUDIO_EXTENSIONS): AUDIO_FILE = f
        if SRT_FILE and AUDIO_FILE: break
    
    if not SRT_FILE or not AUDIO_FILE: return False
    OUTPUT_FILE = f"{os.path.splitext(SRT_FILE)[0]}.mp4"
    return True

def parse_srt_and_create_list():
    print(f"\n[INFO] টাইমিং লিস্ট তৈরি হচ্ছে...")

    with open(SRT_FILE, 'r', encoding='utf-8-sig') as f: lines = f.readlines()
    time_pattern = re.compile(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})')
    
    entries = []
    curr_num = None
    for line in lines:
        line = line.strip()
        if line.isdigit(): curr_num = line; continue
        m = time_pattern.match(line)
        if m and curr_num:
            entries.append({'number': curr_num, 'start': time_str_to_seconds(m.group(1))})
            curr_num = None
    
    if not entries: return False

    list_content = []
    for i, entry in enumerate(entries):
        img = find_image_file(entry['number'])
        if not img: continue
        
        if i == len(entries) - 1:
            duration = 5.0 
        else:
            duration = entries[i+1]['start'] - entry['start']
        
        if duration < 0.04: duration = 0.04 

        list_content.append(f"file '{os.path.normpath(img)}'")
        list_content.append(f"duration {duration:.3f}")

    if list_content:
        list_content.append(list_content[-2])

    with open('list.txt', 'w', encoding='utf-8') as f: f.write('\n'.join(list_content))
    return True

def create_video():
    raw_audio_duration = get_audio_duration(AUDIO_FILE)
    if raw_audio_duration is None: print("[Error] Audio info failed"); return
    
    if not parse_srt_and_create_list(): return
    
    # টার্গেট ডিউরেশন = অডিওর আসল দৈর্ঘ্য (কোনো বাড়তি বাফার নেই)
    TARGET_DURATION = raw_audio_duration + BUFFER_SECONDS
    
    print(f"\n[INFO] টার্গেট ডিউরেশন সেট করা হয়েছে: {TARGET_DURATION}s")
    print("[INFO] রেন্ডারিং হচ্ছে... (Exact Cut Mode)")
    
    command = [
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-i', AUDIO_FILE,
        
        '-filter_complex', 
        # tpad ব্যবহার করে ভিডিও ক্লোন করা হচ্ছে, যাতে -t কমান্ড সঠিক ফ্রেম পায়
        f"[0:v]fps=30,tpad=stop_mode=clone:stop_duration=20[v_out];[1:a]apad[a_out]",
        
        '-map', '[v_out]', 
        '-map', '[a_out]',
        
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', 
        
        # হার্ড কাট: ঠিক অডিওর দৈর্ঘ্যে গিয়ে ভিডিও শেষ হবে
        '-t', str(TARGET_DURATION), 
        
        OUTPUT_FILE
    ]
    
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8')
        for line in process.stdout:
             if "frame=" in line:
                print(f"{line.strip()}", end='\r')
        process.wait()

        if process.returncode == 0:
            print(f"\n\n[SUCCESS] ভিডিও তৈরি সম্পন্ন! ফাইল: {OUTPUT_FILE}")
            print(f"[NOTE] ভিডিওটি এখন অডিওর সাথে একদম পারফেক্ট ম্যাচ করবে।")
        else:
            print(f"\n[ERROR] ভিডিও তৈরিতে সমস্যা হয়েছে।")

    except Exception as e:
        print(f"\n[ERROR] সমস্যা: {e}")
    finally:
        if os.path.exists('list.txt'): os.remove('list.txt')

def cleanup():
    if CONVERT_IMAGES and os.path.exists(CONVERTED_DIR):
        try: shutil.rmtree(CONVERTED_DIR)
        except: pass

if __name__ == "__main__":
    if setup_and_adjust_files():
        if preprocess_images():
            create_video()
    cleanup()
    input("\n[EXIT] বের হতে Enter চাপুন...")
