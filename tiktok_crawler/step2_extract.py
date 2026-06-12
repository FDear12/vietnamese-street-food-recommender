# step2_extract.py — EasyOCR version (DEBUG only)
import os
import cv2
import json
import shutil
import subprocess
import imagehash
import easyocr
import re
import time
from PIL import Image
from pathlib import Path
from config import (
    META_FILE,
    BLUR_THRESHOLD, PHASH_THRESHOLD, FPS_EXTRACT,
)

# ─── CONFIG PATH ──────────────────────────────────────
DEBUG_DIR    = "debug_frames"
COOKIES_TXT  = "cookies.txt"
COOKIES_JSON = "cookies.json"

# ─── INIT EASYOCR ─────────────────────────────────────
print("⏳ Đang load EasyOCR (vi + en)...")
reader = easyocr.Reader(['vi', 'en'], gpu=False, verbose=False)
print("✅ EasyOCR loaded!\n")

# ─── HELPER: META ─────────────────────────────────────

def load_meta() -> list[dict]:
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_meta(records: list[dict]):
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

# ─── HELPER: COOKIES ──────────────────────────────────

def convert_cookies_to_netscape(json_path: str, netscape_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    with open(netscape_path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            domain  = c.get("domain", "")
            flag    = "TRUE" if domain.startswith(".") else "FALSE"
            path    = c.get("path", "/")
            secure  = "TRUE" if c.get("secure", False) else "FALSE"
            expires = max(0, int(c.get("expires", 0)))
            name    = c.get("name", "")
            value   = c.get("value", "")
            f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
    print(f"✅ Convert {len(cookies)} cookies → {netscape_path}")

# ─── HELPER: VIDEO ────────────────────────────────────

def download_video(video_url: str, out_path: str) -> bool:
    try:
        result = subprocess.run(
            ["python", "-m", "yt_dlp",
             "--cookies", COOKIES_TXT,
             "--no-playlist",
             "-f", "mp4/best",
             "-o", out_path,
             "--quiet",
             video_url],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  ✗ yt-dlp stderr: {result.stderr[:300]}")
            return False
        return os.path.exists(out_path)
    except Exception as e:
        print(f"  ✗ Download lỗi: {e}")
        return False

def extract_frames(video_path: str, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    out_pattern = os.path.join(out_dir, "frame_%04d.jpg")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={FPS_EXTRACT}",
        "-q:v", "2", "-y",
        out_pattern
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
        frames = sorted(Path(out_dir).glob("frame_*.jpg"))
        return [str(f) for f in frames]
    except Exception as e:
        print(f"  ✗ ffmpeg lỗi: {e}")
        return []

# ─── HELPER: FILTER ───────────────────────────────────

def is_blur(frame_path: str) -> bool:
    img = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return True
    return cv2.Laplacian(img, cv2.CV_64F).var() < BLUR_THRESHOLD

def is_duplicate(img_path: str, seen_hashes: list) -> bool:
    try:
        h = imagehash.phash(Image.open(img_path))
        for seen in seen_hashes:
            if abs(h - seen) < PHASH_THRESHOLD:
                return True
        seen_hashes.append(h)
        return False
    except:
        return True

# ─── HELPER: TEXT DEDUP ───────────────────────────────

def normalize_text(text: str) -> set:
    """Chuẩn hóa text → set words, bỏ số và ký tự đặc biệt."""
    text = re.sub(r'[^a-záàảãạăắặằẳẵâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ ]', ' ', text.lower())
    return set(text.split())

def jaccard_similarity(text_a: str, text_b: str) -> float:
    a = normalize_text(text_a)
    b = normalize_text(text_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def dedup_texts(ocr_results: list[tuple], threshold: float = 0.6) -> list[tuple]:
    """
    OCR hết video xong → check 1 lần sau.
    ocr_results: list of (frame_path, text_found)
    Trả về list đã lọc trùng.
    """
    kept   = []
    dup_count = 0
    for frame_path, text_found in ocr_results:
        is_dup = any(jaccard_similarity(text_found, kept_text) >= threshold
                     for _, kept_text in kept)
        if is_dup:
            dup_count += 1
            print(f"    ~ {Path(frame_path).name} | text trùng, bỏ")
        else:
            kept.append((frame_path, text_found))
    print(f"  → Dedup text: giữ {len(kept)} | bỏ {dup_count}")
    return kept

# ─── HELPER: OCR ──────────────────────────────────────

def ocr_scan(frame_path: str) -> tuple[bool, str]:
    """Trả về (has_text, text_found)."""
    try:
        result = reader.readtext(frame_path)
        if not result:
            return False, ""
        lines = [text for (_, text, conf) in result if conf > 0.3]
        if not lines:
            return False, ""
        full_text = " ".join(lines).lower()
        return True, full_text[:200]
    except Exception as e:
        print(f"    ⚠ OCR exception: {e}")
        return False, ""

# ─── PROCESS 1 VIDEO ──────────────────────────────────

def process_video(rec: dict, tmp_base: str) -> list[dict]:
    video_id      = rec["video_id"]
    hashtag  = rec["hashtag_chinh"]
    tmp_video_dir = os.path.join(tmp_base, video_id)
    os.makedirs(tmp_video_dir, exist_ok=True)
    video_path    = os.path.join(tmp_video_dir, "video.mp4")

    debug_filtered_dir = Path(DEBUG_DIR) / hashtag / video_id / "text_filtered"
    debug_filtered_dir.mkdir(parents=True, exist_ok=True)

    # 1. Download
    print(f"  → 📥 Downloading...")
    if not download_video(rec["url"], video_path):
        print(f"  ✗ Download thất bại")
        shutil.rmtree(tmp_video_dir, ignore_errors=True)
        return []
    size_mb = os.path.getsize(video_path) / 1024 / 1024
    print(f"  → ✅ Downloaded ({size_mb:.1f} MB)")

    # 2. Extract frames
    print(f"  → 🎬 Extract frames...")
    raw_frames = extract_frames(video_path, tmp_video_dir)
    print(f"  → Extract: {len(raw_frames)} frame")
    os.remove(video_path)

    if not raw_frames:
        shutil.rmtree(tmp_video_dir, ignore_errors=True)
        return []

    # 3. Filter blur + dedup ảnh
    seen_hashes  = []
    clean_frames = []
    blur_count = dup_count = 0
    for f in raw_frames:
        if is_blur(f):
            blur_count += 1
            continue
        if is_duplicate(f, seen_hashes):
            dup_count += 1
            continue
        clean_frames.append(f)

    print(f"  → Sau filter: {len(clean_frames)} sạch | blur={blur_count} | dup={dup_count}")

    if not clean_frames:
        shutil.rmtree(tmp_video_dir, ignore_errors=True)
        return []

    # 4. OCR hết video trước
    print(f"  → 🔍 OCR scan {len(clean_frames)} frames...")
    ocr_results = []
    for frame_path in clean_frames:
        has_text, text_found = ocr_scan(frame_path)
        fname = Path(frame_path).name
        if not has_text:
            print(f"    ✗ {fname} | no text")
            continue
        print(f"    ✓ {fname} | '{text_found[:60]}'")
        ocr_results.append((frame_path, text_found))

    if not ocr_results:
        shutil.rmtree(tmp_video_dir, ignore_errors=True)
        return []

    # 5. Dedup text sau khi OCR hết video (Jaccard, ngưỡng 0.6)
    filtered = dedup_texts(ocr_results, threshold=0.6)

    # 6. Lưu kết quả
    frames_meta = []
    for frame_path, text_found in filtered:
        fname = Path(frame_path).name
        shutil.copy2(frame_path, debug_filtered_dir / fname)
        frames_meta.append({
            "name"    : fname,
            "ocr_text": text_found,
        })

    print(f"  → Giữ lại: {len(frames_meta)} frame")

    # 7. Dọn tmp
    shutil.rmtree(tmp_video_dir, ignore_errors=True)
    return frames_meta

# ─── MAIN ─────────────────────────────────────────────

def main():
    convert_cookies_to_netscape(COOKIES_JSON, COOKIES_TXT)

    records = load_meta()
    total   = len(records)
    print(f"\n📂 Tổng video cần xử lý: {total}\n")

    tmp_base = "tmp_frames"
    os.makedirs(tmp_base, exist_ok=True)

    done = skipped = no_frame = 0
    start_total = time.time()
    processed = 0  # số video thực sự xử lý (không tính skip)

    for i, rec in enumerate(records):
        video_id = rec["video_id"]
        hashtag  = rec["hashtag_chinh"]

        if rec.get("frames") is not None:
            print(f"[{i+1}/{total}] {video_id} → đã xử lý, bỏ qua")
            skipped += 1
            continue

        print(f"\n[{i+1}/{total}] {video_id} | #{hashtag}")
        start = time.time()

        frames_meta = process_video(rec, tmp_base)
        elapsed = time.time() - start

        if frames_meta:
            rec["frames"] = frames_meta
            done += 1
            print(f"  ✓ Lưu {len(frames_meta)} frame vào metadata")
        else:
            rec["frames"] = []
            no_frame += 1
            print(f"  ✗ Không có frame nào hợp lệ")

        processed += 1
        save_meta(records)

        # Thống kê thời gian
        avg = (time.time() - start_total) / processed
        remaining = (total - skipped - processed) * avg
        h, m = int(remaining // 3600), int((remaining % 3600) // 60)
        print(f"  ⏱ Video này: {elapsed:.1f}s | Trung bình: {avg:.1f}s | Còn lại: ~{h}h{m:02d}m")
        print(f"  → Tiến độ: {i+1}/{total} | Done: {done} | Bỏ: {no_frame} | Skip: {skipped}")

    shutil.rmtree(tmp_base, ignore_errors=True)

    total_time = time.time() - start_total
    h, m, s = int(total_time // 3600), int((total_time % 3600) // 60), int(total_time % 60)
    print(f"\n✅ XONG! Tổng thời gian: {h}h{m:02d}m{s:02d}s")
    print(f"  Có frame : {done}")
    print(f"  Không có : {no_frame}")
    print(f"  Skip     : {skipped}")
    print(f"\n  📁 Debug → {DEBUG_DIR}/<video_id>/text_filtered/")


if __name__ == "__main__":
    main()