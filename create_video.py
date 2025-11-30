import os
import subprocess
import re
import math
import shutil

# =================================================================
#               কনফিগারেশন (Configuration)
# =================================================================
# --- ইমেজ কনভার্সন সেটিংস ---
CONVERT_IMAGES = True  # True দিলে ভিডিও তৈরির আগে সব ছবি কনভার্ট হবে
TARGET_RESOLUTION = '1920x1080' # আপনার পছন্দের রেজোলিউশন (e.g., '1280x720')
TARGET_EXTENSION = 'jpg'        # সব ছবি এই ফরম্যাটে কনভার্ট হবে (jpg is recommended)
CONVERTED_DIR = 'converted_images' # কনভার্ট করা ছবি রাখার ফোল্ডার

# --- ফাইল সেটিংস (এগুলো স্বয়ংক্রিয়ভাবে সনাক্ত হবে) ---
SRT_FILE = '' 
AUDIO_FILE = ''
OUTPUT_FILE = ''

# --- সাপোর্টেড ফরম্যাটের তালিকা ---
SUPPORTED_IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff']
SUPPORTED_AUDIO_EXTENSIONS = ['mp3', 'wav', 'aac', 'm4a', 'ogg', 'flac']
# =================================================================

def get_image_numbers_from_srt():
    """শুধু SRT ফাইল থেকে ছবির নম্বরগুলোর একটি তালিকা তৈরি করে।"""
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
    """ভিডিও তৈরির আগে সমস্ত ছবিকে নির্দিষ্ট রেজোলিউশন ও ফরম্যাটে কনভার্ট করে।"""
    if not CONVERT_IMAGES:
        return True

    print("\n" + "="*60)
    print("[INFO] ইমেজ প্রি-প্রসেসিং শুরু হচ্ছে...")
    print(f"[INFO] সমস্ত ছবিকে '{TARGET_RESOLUTION}' রেজোলিউশন এবং '.{TARGET_EXTENSION}' ফরম্যাটে কনভার্ট করা হবে।")
    print("="*60)

    if not os.path.exists(CONVERTED_DIR):
        os.makedirs(CONVERTED_DIR)

    image_numbers = get_image_numbers_from_srt()
    if not image_numbers:
        print("[FATAL ERROR] SRT ফাইল থেকে কোনো ছবির নম্বর পাওয়া যায়নি।")
        return False

    try:
        target_w, target_h = TARGET_RESOLUTION.split('x')
        int(target_w); int(target_h)
    except ValueError:
        print(f"[FATAL ERROR] TARGET_RESOLUTION '{TARGET_RESOLUTION}' এর ফরম্যাটটি ভুল। দয়া করে '1920x1080' এর মতো ফরম্যাট ব্যবহার করুন।")
        return False

    total_images = len(image_numbers)
    for i, number in enumerate(image_numbers):
        original_image_path = find_original_image_file(number)
        
        if not original_image_path:
            print(f"[WARNING] মূল ইমেজ নম্বর '{number}' খুঁজে পাওয়া যায়নি। এটিকে স্কিপ করা হচ্ছে।")
            continue

        converted_image_path = os.path.join(CONVERTED_DIR, f"{number}.{TARGET_EXTENSION}")
        
        if os.path.exists(converted_image_path):
            print(f"({i+1}/{total_images}) ইমেজ '{number}' আগে থেকেই কনভার্ট করা আছে। স্কিপ করা হচ্ছে।")
            continue

        print(f"({i+1}/{total_images}) কনভার্ট করা হচ্ছে: '{original_image_path}' -> '{converted_image_path}'")
        
        vf_filter = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black"
        command = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-i', original_image_path,
            '-vf', vf_filter,
            converted_image_path
        ]
        
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"\n[FATAL ERROR] '{original_image_path}' কনভার্ট করার সময় FFMPEG এরর দিয়েছে।")
            if e.stderr:
                print(f"FFMPEG Error: {e.stderr.decode('utf-8')}")
            return False

    print("\n[SUCCESS] সমস্ত ছবি সফলভাবে প্রি-প্রসেস করা হয়েছে।")
    return True

def find_original_image_file(number):
    """বিভিন্ন ফরম্যাটের মধ্যে মূল ছবির ফাইলটি খুঁজে বের করে।"""
    for ext in SUPPORTED_IMAGE_EXTENSIONS:
        filename = f"{number}.{ext}"
        if os.path.exists(filename):
            return filename
    return None

def find_image_file(number):
    """কনভার্ট করা অথবা মূল ছবির ফাইল পাথ রিটার্ন করে।"""
    if CONVERT_IMAGES:
        converted_path = os.path.join(CONVERTED_DIR, f"{number}.{TARGET_EXTENSION}")
        if os.path.exists(converted_path):
            return converted_path
    return find_original_image_file(number)

def get_audio_duration(audio_file_path):
    command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_file_path]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None

def seconds_to_srt_time(seconds):
    if seconds < 0: seconds = 0
    hours = math.floor(seconds / 3600); minutes = math.floor((seconds % 3600) / 60)
    secs = math.floor(seconds % 60); millis = round((seconds - math.floor(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def setup_and_adjust_files():
    global SRT_FILE, AUDIO_FILE, OUTPUT_FILE
    for file in os.listdir('.'):
        if not SRT_FILE and file.lower().endswith('.srt'): SRT_FILE = file
        if not AUDIO_FILE and any(file.lower().endswith(f".{ext}") for ext in SUPPORTED_AUDIO_EXTENSIONS): AUDIO_FILE = file
        if SRT_FILE and AUDIO_FILE: break
    if not SRT_FILE or not AUDIO_FILE: return False
    
    OUTPUT_FILE = f"{os.path.splitext(SRT_FILE)[0]}.mp4"
    print("="*60); print(f"[INFO] ফাইল সনাক্ত করা হয়েছে:\n       সাবটাইটেল: {SRT_FILE}\n       অডিও: {AUDIO_FILE}\n       আউটপুট: {OUTPUT_FILE}"); print("="*60)

    duration_sec = get_audio_duration(AUDIO_FILE)
    if duration_sec is None: return False
    new_end_time_str = seconds_to_srt_time(duration_sec)
    
    try:
        with open(SRT_FILE, 'r', encoding='utf-8-sig') as f: lines = f.readlines()
        last_time_line_index = -1
        for i in range(len(lines) - 1, -1, -1):
            if '-->' in lines[i]: last_time_line_index = i; break
        if last_time_line_index == -1: return False
        
        parts = lines[last_time_line_index].strip().split('-->')
        new_line = f"{parts[0].strip()} --> {new_end_time_str}\n"
        if lines[last_time_line_index].strip() != new_line.strip():
            print(f"[INFO] অডিওর দৈর্ঘ্য ({new_end_time_str}) অনুযায়ী SRT ফাইলের শেষ সময় আপডেট করা হচ্ছে...")
            lines[last_time_line_index] = new_line
            with open(SRT_FILE, 'w', encoding='utf-8') as f: f.writelines(lines)
    except Exception: return False
    return True

def time_str_to_seconds(time_str):
    try:
        h, m, s_ms = time_str.split(':'); s, ms = s_ms.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    except ValueError: return 0

def parse_srt_and_create_list():
    print(f"\n[INFO] '{SRT_FILE}' ফাইলটি প্রসেস করে 'list.txt' তৈরি করা হচ্ছে...")
    with open(SRT_FILE, 'r', encoding='utf-8-sig') as f: lines = f.readlines()
    time_pattern = re.compile(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})')
    entries, current_number = [], None
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.isdigit(): current_number = line; continue
        time_match = time_pattern.match(line)
        if time_match and current_number:
            start_str, end_str = time_match.groups()
            entries.append({'number': current_number, 'start_sec': time_str_to_seconds(start_str), 'end_sec': time_str_to_seconds(end_str)})
            current_number = None
    
    list_content = []
    for i, entry in enumerate(entries):
        img_file = find_image_file(entry['number'])
        if not img_file: print(f"[WARNING] ইমেজ নম্বর '{entry['number']}' খুঁজে পাওয়া যায়নি। স্কিপ করা হচ্ছে।"); continue
        duration = (entries[i+1]['start_sec'] if i < len(entries) - 1 else entry['end_sec']) - entry['start_sec']
        if duration <= 0: continue
        list_content.append(f"file '{os.path.normpath(img_file)}'"); list_content.append(f"duration {duration:.3f}")

    if not list_content: print("[FATAL ERROR] 'list.txt' এর জন্য কোনো কার্যকর ইমেজ এন্ট্রি পাওয়া যায়নি।"); return False
    with open('list.txt', 'w', encoding='utf-8') as f: f.write('\n'.join(list_content)); return True

def create_video():
    if not parse_srt_and_create_list(): return
    print("\n[INFO] এখন ffmpeg ব্যবহার করে চূড়ান্ত ভিডিও তৈরি করা হচ্ছে...")
    
    # >>>>>>>> এই কমান্ডটি পরিবর্তন করা হয়েছে - এখন প্রসেসিং ধাপ দেখা যাবে <<<<<<<<
    command = [
        'ffmpeg', '-y',
        '-f', 'concat', 
        '-safe', '0', 
        '-i', 'list.txt', 
        '-i', AUDIO_FILE, 
        '-c:v', 'libx264', 
        '-c:a', 'aac', 
        '-pix_fmt', 'yuv420p',
        '-r', '25',
        OUTPUT_FILE
    ]
    
    try:
        # >>>>>>>> এই অংশটি পরিবর্তন করা হয়েছে - এখন লাইভ আউটপুট দেখা যাবে <<<<<<<<
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8')
        for line in process.stdout:
            print(line.strip())
        process.wait()
        
        if process.returncode == 0:
            print("\n" + "="*60); print(f" SUCCESS: ভিডিও সফলভাবে তৈরি হয়েছে: {OUTPUT_FILE}"); print("="*60)
        else:
            print(f"\n[FATAL ERROR] FFMPEG একটি এরর দিয়েছে। দয়া করে উপরের লগ দেখুন।")

    except Exception as e:
        print(f"\n[FATAL ERROR] একটি অপ্রত্যাশিত সমস্যা হয়েছে: {e}")
    finally:
        if os.path.exists('list.txt'): os.remove('list.txt')

def cleanup():
    """কাজ শেষে অস্থায়ী ফোল্ডার স্বয়ংক্রিয়ভাবে ডিলিট করে।"""
    if CONVERT_IMAGES and os.path.exists(CONVERTED_DIR):
        try:
            # >>>>>>>> এই অংশটি পরিবর্তন করা হয়েছে - এখন স্বয়ংক্রিয়ভাবে ডিলিট হবে <<<<<<<<
            print(f"\n[INFO] অস্থায়ী '{CONVERTED_DIR}' ফোল্ডারটি স্বয়ংক্রিয়ভাবে ডিলিট করা হচ্ছে...")
            shutil.rmtree(CONVERTED_DIR)
            print(f"[INFO] ফোল্ডারটি সফলভাবে ডিলিট করা হয়েছে।")
        except Exception as e:
            print(f"[ERROR] '{CONVERTED_DIR}' ফোল্ডার ডিলিট করার সময় সমস্যা হয়েছে: {e}")

# --- মূল চালিকা ---
if __name__ == "__main__":
    if setup_and_adjust_files():
        if preprocess_images():
            create_video()
    
    cleanup()
    input("\nকাজ শেষ। বের হওয়ার জন্য Enter চাপুন...")