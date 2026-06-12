# step3_pack.py — Pack ZIP theo từng batch hashtag
import os
import json
import zipfile
from pathlib import Path
from config import META_FILE

# ─── CONFIG ───────────────────────────────────────────
DEBUG_DIR  = "debug_frames"
BATCH_SIZE = 3   # số hashtag mỗi zip, chỉnh tùy ý

# ─── HELPER ───────────────────────────────────────────

def load_meta() -> list[dict]:
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def pack_batch(batch_hashtags: list[str], valid: list[dict], batch_idx: int):
    output_zip = f"images_batch{batch_idx:02d}.zip"
    batch_records = [r for r in valid if r["hashtag_chinh"] in batch_hashtags]

    if not batch_records:
        print(f"  ⚠ Batch {batch_idx} không có record nào, bỏ qua")
        return

    clean_meta = []
    for rec in batch_records:
        clean_meta.append({
            "video_id"       : rec["video_id"],
            "url"            : rec["url"],
            "hashtag_chinh"  : rec["hashtag_chinh"],
            "ngay_dang"      : rec.get("ngay_dang", "unknown"),
            "hashtags_useful": rec.get("hashtags_useful", []),
            "hashtags_raw"   : rec.get("hashtags_raw", []),
            "frames"         : rec["frames"],
        })

    packed = missing = 0
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # metadata.json
        meta_bytes = json.dumps(clean_meta, ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr("metadata.json", meta_bytes)

        # ảnh: images/<hashtag>/<video_id>_<frame>
        for rec in batch_records:
            video_id = rec["video_id"]
            hashtag  = rec["hashtag_chinh"]
            src_dir  = Path(DEBUG_DIR) / hashtag / video_id / "text_filtered"

            for frame in rec["frames"]:
                fname    = frame["name"]
                src_path = src_dir / fname
                zip_path = f"images/{hashtag}/{video_id}_{fname}"

                if src_path.exists():
                    zf.write(str(src_path), zip_path)
                    packed += 1
                else:
                    print(f"    ⚠ Không tìm thấy: {src_path}")
                    missing += 1

    size_mb = os.path.getsize(output_zip) / 1024 / 1024
    print(f"  ✅ {output_zip} | hashtag: {batch_hashtags} | {packed} ảnh | {size_mb:.1f} MB")


# ─── MAIN ─────────────────────────────────────────────

def main():
    records = load_meta()
    valid   = [r for r in records if r.get("frames")]
    print(f"📂 Tổng: {len(records)} | Hợp lệ: {len(valid)} | Bỏ: {len(records)-len(valid)}\n")

    if not valid:
        print("❌ Không có record hợp lệ!")
        return

    # Lấy danh sách hashtag theo thứ tự xuất hiện
    seen = []
    for r in valid:
        h = r["hashtag_chinh"]
        if h not in seen:
            seen.append(h)
    hashtags = seen

    print(f"📋 Tổng {len(hashtags)} hashtag: {hashtags}")
    print(f"📦 Chia thành batch {BATCH_SIZE} hashtag/zip\n")

    # Chia batch và pack
    for i in range(0, len(hashtags), BATCH_SIZE):
        batch = hashtags[i: i + BATCH_SIZE]
        batch_idx = (i // BATCH_SIZE) + 1
        print(f"[Batch {batch_idx}] {batch}")
        pack_batch(batch, valid, batch_idx)

    print(f"\n✅ XONG! Upload từng file images_batch*.zip lên Google Drive nhé!")


if __name__ == "__main__":
    main()