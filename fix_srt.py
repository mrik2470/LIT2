import os
import re

# =================================================================
#               SMART SRT Subtitle Fixer (Fixed hour->minute bug)
# =================================================================

def color(text, c):
    colors = {"red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m", "reset": "\033[0m"}
    return f"{colors.get(c,'')}{text}{colors['reset']}"

def parse_time_components(time_str):
    """HH:MM:SS,ms → (hour, minute, second, millisecond)"""
    try:
        time_str = time_str.strip()
        main, ms = time_str.split(",")
        h, m, s = main.split(":")
        return int(h), int(m), int(s), int(ms)
    except Exception:
        return 0, 0, 0, 0

def format_time(h, m, s, ms):
    return f"{str(h).zfill(2)}:{str(m).zfill(2)}:{str(s).zfill(2)},{str(ms).zfill(3)}"

def total_seconds(h, m, s):
    return h * 3600 + m * 60 + s

def analyze_and_fix_srt(file_path):
    print(color("\n[INFO] স্মার্ট SRT বিশ্লেষণ ও সংশোধন শুরু...", "yellow"))
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()

        # Collect timestamp entries (with their line index)
        ts_pattern = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")
        entries = []
        for idx, line in enumerate(lines):
            m = ts_pattern.search(line)
            if m:
                entries.append({
                    "idx": idx,
                    "start": m.group(1),
                    "end": m.group(2),
                    "orig": line
                })

        if not entries:
            print(color("[INFO] কোনো টাইমস্ট্যাম্প পাওয়া যায়নি।", "yellow"))
            return True

        # Heuristic: count how many timestamps have hour>0 and minute==0
        hour_zero_count = 0
        for e in entries:
            sh, sm, ss, sms = parse_time_components(e["start"])
            eh, em, es, ems = parse_time_components(e["end"])
            if sh > 0 and sm == 0:
                hour_zero_count += 1
            if eh > 0 and em == 0:
                hour_zero_count += 1

        total_ts = len(entries) * 2
        # threshold: at least a few occurrences or a small fraction of timestamps
        threshold = max(3, int(total_ts * 0.03))
        systemic = hour_zero_count >= threshold

        if systemic:
            print(color(f"  -> সিস্টেমিক hour→minute ত্রুটি সনাক্ত (count={hour_zero_count}) — ব্যাপক সংশোধন চালানো হবে।", "red"))
        else:
            print(color(f"  -> hour→minute ত্রুটি সীমিত (count={hour_zero_count}) — কনটেক্সট-ভিত্তিক সংশোধন করা হবে।", "yellow"))

        corrections = 0

        # 1) First handle pairwise "59s then next hour" transitions robustly.
        # If previous ended at H:00:59 and next started at H+1:00:00, it's likely minutes were in hours.
        for i in range(len(entries) - 1):
            prev = entries[i]
            curr = entries[i + 1]

            # parse prev end and curr start
            ph, pm, ps, pms = parse_time_components(prev["end"])
            ch, cm, cs, cms = parse_time_components(curr["start"])

            if ps >= 59 and ph > 0 and pm == 0 and ch == ph + 1 and cm == 0:
                # convert both: hour -> minute (take modulo 60 just in case)
                new_prev_end = format_time(0, ph % 60, ps, pms)
                new_curr_start = format_time(0, ch % 60, cs, cms)

                if prev["end"] != new_prev_end:
                    print(color(f"  -> জোড়া কেস সংশোধন (prev end): {prev['end']} → {new_prev_end}", "yellow"))
                    prev["end"] = new_prev_end
                    corrections += 1
                if curr["start"] != new_curr_start:
                    print(color(f"  -> জোড়া কেস সংশোধন (curr start): {curr['start']} → {new_curr_start}", "yellow"))
                    curr["start"] = new_curr_start
                    corrections += 1

        # 2) If systemic, convert lone hour:minute==0 cases to minute = hour (e.g., 01:00 -> 00:01)
        #    If not systemic, still convert when minute==0 AND that makes start<=end or fits neighbor context.
        for i, e in enumerate(entries):
            # handle both start and end
            for side in ("start", "end"):
                orig = e[side]
                h, m, s, ms = parse_time_components(orig)
                new_h, new_m = h, m

                converted = False
                if h > 0 and m == 0 and h < 60:
                    if systemic:
                        new_h = 0
                        new_m = h % 60
                        converted = True
                    else:
                        # context-based: check neighbors and same-line relation
                        # a) If converting makes start <= end for same line, accept
                        if side == "start":
                            # check end of same entry
                            eh, em, es, ems = parse_time_components(e["end"])
                            cand_start_sec = total_seconds(0, h % 60, s)
                            end_sec = total_seconds(eh, em, es)
                            if cand_start_sec <= end_sec:
                                new_h = 0
                                new_m = h % 60
                                converted = True
                        else:
                            # side == "end"
                            sh, sm, ss, sms = parse_time_components(e["start"])
                            cand_end_sec = total_seconds(0, h % 60, s)
                            start_sec = total_seconds(sh, sm, ss)
                            if cand_end_sec >= start_sec:
                                new_h = 0
                                new_m = h % 60
                                converted = True

                        # b) neighbor-based: if previous/next has similar pattern, allow convert
                        if not converted:
                            # prev neighbor
                            if i > 0:
                                ph, pm, ps, pms = parse_time_components(entries[i - 1]["end"])
                                if ps >= 50 and ph > 0 and pm == 0:
                                    new_h = 0
                                    new_m = h % 60
                                    converted = True
                            # next neighbor
                            if not converted and i < len(entries) - 1:
                                nh, nm, ns, nms = parse_time_components(entries[i + 1]["start"])
                                if ns <= 5 and nh > 0 and nm == 0:
                                    new_h = 0
                                    new_m = h % 60
                                    converted = True

                # apply conversion if determined
                if converted:
                    new_val = format_time(new_h, new_m, s, ms)
                    if new_val != orig:
                        print(color(f"  -> সংশোধন: {orig} → {new_val}", "yellow"))
                        e[side] = new_val
                        corrections += 1

                # also ensure minutes < 60 (carry over if needed)
                hh, mm, ss, mss = parse_time_components(e[side])
                if mm >= 60:
                    carry = mm // 60
                    mm = mm % 60
                    hh += carry
                    new_val = format_time(hh, mm, ss, mss)
                    if new_val != e[side]:
                        print(color(f"  -> মিনিট overflow সংশোধন: {e[side]} → {new_val}", "yellow"))
                        e[side] = new_val
                        corrections += 1

        # 3) Final sanity: within each entry, if start > end in seconds, try reasonable fixes:
        for e in entries:
            sh, sm, ss, sms = parse_time_components(e["start"])
            eh, em, es, ems = parse_time_components(e["end"])
            start_sec = total_seconds(sh, sm, ss)
            end_sec = total_seconds(eh, em, es)
            if start_sec > end_sec:
                # if end has hour>0 and minute==0, try converting end hour->minute
                if eh > 0 and em == 0 and eh < 60:
                    new_end = format_time(0, eh % 60, es, ems)
                    print(color(f"  -> স্যানিটি ফিক্স: start>{end}, চেষ্টা করে end hour→minute: {e['end']} → {new_end}", "yellow"))
                    e["end"] = new_end
                    corrections += 1
                else:
                    # as last resort, if end is earlier but within 2 minutes, bump end minute forward
                    if end_sec + 120 >= start_sec:
                        # set end = start + 1 sec
                        ns = start_sec + 1
                        nh = ns // 3600
                        nm = (ns % 3600) // 60
                        nsec = ns % 60
                        new_end = format_time(nh, nm, nsec, ems)
                        print(color(f"  -> স্যানিটি রেজলভ: end ছোট → set end = start+1s: {e['end']} → {new_end}", "yellow"))
                        e["end"] = new_end
                        corrections += 1

        # Write back changes into lines
        for e in entries:
            lines[e["idx"]] = f"{e['start']} --> {e['end']}\n"

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        if corrections:
            print(color(f"\n[SUCCESS] মোট {corrections}টি টাইমস্ট্যাম্প সংশোধন করা হয়েছে।", "green"))
        else:
            print(color("\n[SUCCESS] কোনো স্বীকৃত ত্রুটি পাওয়া যায়নি।", "green"))

    except Exception as ex:
        print(color(f"[ERROR] ফাইল প্রসেসিংয়ে সমস্যা: {ex}", "red"))
        return False

    return True

# --- Main Driver ---
if __name__ == "__main__":
    print("=" * 70)
    print("      SMART SRT Subtitle Auto-Fixer (bug-fixed hour->minute)      ")
    print("=" * 70)

    srt_file = next((f for f in os.listdir('.') if f.lower().endswith('.srt')), None)

    if srt_file:
        print(color(f"\n[INFO] ফাইল পাওয়া গেছে: {srt_file}", "green"))
        print(color("[WARNING] এটি মূল ফাইলকে সরাসরি আপডেট করবে। ব্যাকআপ রেখে চালালে নিরাপদ।", "yellow"))
        if analyze_and_fix_srt(srt_file):
            print(color(f"\n[DONE] '{srt_file}' সফলভাবে আপডেট হয়েছে!", "green"))
        else:
            print(color("[FAILED] কোনো সমস্যা ঘটেছে।", "red"))
    else:
        print(color("[ERROR] কোনো .srt ফাইল পাওয়া যায়নি।", "red"))

    input("\nবের হতে Enter চাপুন...")
