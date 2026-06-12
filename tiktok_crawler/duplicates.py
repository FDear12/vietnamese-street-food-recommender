import json
from collections import defaultdict

DATA_PATH = "data.json"

with open(DATA_PATH, encoding="utf-8") as f:
    records = json.load(f)

# Nhóm theo (hashtag_chinh, diachi_check) — chỉ record diachi_match=True
groups = defaultdict(list)
for i, r in enumerate(records):
    if r.get("diachi_match") is True:
        key = (r.get("hashtag_chinh", ""), r.get("diachi_check", ""))
        groups[key].append(i)

to_remove = set()
merged_count = 0

for (hashtag, diachi), indices in groups.items():
    if len(indices) < 2:
        continue

    merged_count += 1
    keep_idx = indices[0]
    keep = records[keep_idx]

    print(f"Gộp: [{hashtag}] {diachi}")
    print(f"  Giữ : {keep.get('video_id')} | {keep.get('tenquan')}")

    for dup_idx in indices[1:]:
        dup = records[dup_idx]
        print(f"  Bỏ  : {dup.get('video_id')} | {dup.get('tenquan')}")

        # Merge hashtags_useful
        hu_keep = keep.get("hashtags_useful") or []
        hu_dup  = dup.get("hashtags_useful") or []
        keep["hashtags_useful"] = list(dict.fromkeys(hu_keep + [t for t in hu_dup if t not in hu_keep]))

        # Merge hashtags_raw
        hr_keep = keep.get("hashtags_raw") or []
        hr_dup  = dup.get("hashtags_raw") or []
        keep["hashtags_raw"] = list(dict.fromkeys(hr_keep + [t for t in hr_dup if t not in hr_keep]))

        # Merge review (dedup theo text)
        import ast
        rv_keep = keep.get("review") or []
        rv_dup  = dup.get("review") or []
        if isinstance(rv_keep, str):
            try: rv_keep = ast.literal_eval(rv_keep)
            except: rv_keep = []
        if isinstance(rv_dup, str):
            try: rv_dup = ast.literal_eval(rv_dup)
            except: rv_dup = []
        seen = {item.get("text", "") for item in rv_keep}
        for item in rv_dup:
            if item.get("text", "") not in seen:
                rv_keep.append(item)
                seen.add(item.get("text", ""))
        keep["review"] = rv_keep

        to_remove.add(dup_idx)

    records[keep_idx] = keep
    print()

new_records = [r for i, r in enumerate(records) if i not in to_remove]

with open(DATA_PATH, "w", encoding="utf-8") as f:
    json.dump(new_records, f, ensure_ascii=False, indent=2)

print(f"Xong. Gộp {merged_count} nhóm, xoá {len(to_remove)} bản trùng.")
print(f"Trước: {len(records)} records → Sau: {len(new_records)} records")