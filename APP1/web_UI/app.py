from flask import Flask, request, render_template, session, jsonify, send_file, abort
from flask_session import Session
from main import generate_response
from detect_route import detect_bp
import json
import os
import glob
import random
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

app.register_blueprint(detect_bp)

DATA_PATH = "data_v2/data.json"
DEBUG_FRAMES_DIR = "data_v2/debug_frames"

with open(DATA_PATH, encoding="utf-8") as f:
    all_records = json.load(f)

all_records = [r for r in all_records if r.get("tenquan")]

CUTOFF_DATE = datetime.now() - timedelta(days=30)


def _is_recent(r: dict) -> bool:
    raw = r.get("cap_nhat_ngay_dang") or r.get("ngay_dang") or ""
    try:
        dt = datetime.strptime(str(raw)[:10], "%Y-%m-%d")
        return dt >= CUTOFF_DATE
    except Exception:
        return False


def get_frame_path(video_id: str, hashtag_chinh: str) -> str | None:
    if not video_id or not hashtag_chinh:
        return None
    folder = os.path.join(DEBUG_FRAMES_DIR, hashtag_chinh, video_id, "text_filtered")
    if not os.path.isdir(folder):
        folder = os.path.join(DEBUG_FRAMES_DIR, hashtag_chinh, video_id)
    if not os.path.isdir(folder):
        return None
    frames = sorted(glob.glob(os.path.join(folder, "frame_*.jpg")))
    if frames:
        return frames[0]
    frames = sorted(glob.glob(os.path.join(folder, "*.jpg")))
    return frames[0] if frames else None


def best_tenquan(r: dict) -> str:
    """diachi_match=True → dùng tenquan_check (đã xác thực), ngược lại tenquan gốc."""
    if r.get("diachi_match") is True:
        return r.get("tenquan_check") or r.get("tenquan") or ""
    return r.get("tenquan") or ""


def best_diachi(r: dict) -> str:
    """diachi_match=True → dùng diachi_check (đã xác thực Google Maps), ngược lại diachi gốc."""
    if r.get("diachi_match") is True:
        return r.get("diachi_check") or r.get("diachi") or ""
    return r.get("diachi") or ""


import ast
import re

def enrich_record(r: dict) -> dict:
    frame_path = get_frame_path(r.get("video_id", ""), r.get("hashtag_chinh", ""))
    r["_has_frame"] = frame_path is not None
    r["_display_tenquan"] = best_tenquan(r)
    r["_display_diachi"]  = best_diachi(r)
    r["_is_recent"] = _is_recent(r)

    # Parse review string → list nếu chưa phải list
    rv = r.get("review")
    if isinstance(rv, str) and rv.strip():
        try:
            parsed = ast.literal_eval(rv)
            if not isinstance(parsed, list):
                parsed = []
        except Exception:
            parsed = []
    elif isinstance(rv, list):
        parsed = rv
    else:
        parsed = []

    # Clean "Giá mỗi người:..." khỏi review text
    cleaned = []
    for item in parsed:
        if isinstance(item, dict):
            text = item.get("text", "") or ""
            text = re.sub(r'\s*Giá mỗi người:.*$', '', text, flags=re.IGNORECASE).strip()
            item["text"] = text
            cleaned.append(item)
    r["review"] = cleaned

    return r


LOCATION_KEYWORDS = {
    "danang":     ["đà nẵng", "da nang", "danang"],
    "hochiminh":  ["hồ chí minh", "ho chi minh", "hcm", "tp.hcm", "tp hcm", "sài gòn", "sai gon"],
    "hanoi":      ["hà nội", "ha noi", "hanoi"],
}


def match_location(r: dict, loc_key: str) -> bool:
    """Kiểm tra record có thuộc thành phố loc_key không."""
    if not loc_key:
        return True
    keywords = LOCATION_KEYWORDS.get(loc_key, [])
    fields = " ".join(filter(None, [
        str(r.get("location_search") or ""),
        str(r.get("diachi_check") or r.get("diachi") or ""),
    ])).lower()
    return any(kw in fields for kw in keywords)


# Các từ phổ biến không mang ý nghĩa tìm kiếm món ăn / địa điểm
SEARCH_STOPWORDS = {
    "quán", "quan", "ngon", "bán", "ban", "ở", "o", "tại", "tai",
    "có", "co", "và", "va", "của", "cua", "cho", "la", "là",
    "nhà", "nha", "hàng", "hang", "ăn", "an", "uống", "uong",
    "nơi", "noi", "chỗ", "cho", "gần", "gan", "đây", "day",
    "đó", "do", "thì", "thi", "mà", "ma", "thôi", "thoi",
    "rất", "rat", "siêu", "sieu", "cực", "cuc", "xịn", "xin",
}

# Bảng alias: từ người dùng hay gõ → keyword chuẩn khớp với hashtag/tên
FOOD_ALIASES = {
    "mì quảng": "miquang",
    "mi quang": "miquang",
    "mỳ quảng": "miquang",
    "my quang": "miquang",
    "bún chả": "buncha",
    "bun cha": "buncha",
    "phở bò": "phobò",
    "pho bo": "phobo",
    "bún bò": "bunbo",
    "bun bo": "bunbo",
    "cơm tấm": "comtam",
    "com tam": "comtam",
    "bánh xèo": "banhxeo",
    "banh xeo": "banhxeo",
    "bún mắm": "bunmam",
    "bun mam": "bunmam",
    "hải sản": "haisan",
    "hai san": "haisan",
    "lẩu": "lau",
    "nướng": "nuong",
    "nuong": "nuong",
    "chè": "che",
    "kem": "kem",
    "bánh mì": "banhmi",
    "banh mi": "banhmi",
}


def _normalize(text: str) -> str:
    """Lowercase và strip dấu cách thừa."""
    return " ".join(text.lower().split())


def _build_ngrams(tokens: list[str]) -> list[str]:
    """Tạo bigrams và trigrams từ danh sách token."""
    bigrams = [tokens[i] + " " + tokens[i + 1] for i in range(len(tokens) - 1)]
    trigrams = [tokens[i] + " " + tokens[i + 1] + " " + tokens[i + 2] for i in range(len(tokens) - 2)]
    return bigrams + trigrams


def search_restaurants(query: str, top_k: int = 20, location: str = ""):
    if not query:
        pool = [r for r in all_records if match_location(r, location)]
        if not pool:
            pool = all_records
        top = sorted(
            pool,
            key=lambda r: (
                -(1 if r.get("diachi_match") else 0),
                -(1 if _is_recent(r) else 0),
                -(r.get("rate") or 0)
            )
        )[:top_k]
        return [enrich_record(dict(r)) for r in top]

    q_norm = _normalize(query)
    tokens = q_norm.split()

    # Unigrams hữu nghĩa (bỏ stopword)
    meaningful_tokens = [t for t in tokens if t not in SEARCH_STOPWORDS]

    # Ngrams (bigram + trigram)
    ngrams = _build_ngrams(tokens)
    meaningful_ngrams = _build_ngrams(meaningful_tokens) if len(meaningful_tokens) > 1 else []

    # Alias mapping: kiểm tra xem toàn bộ query hay ngram có trong bảng alias không
    alias_hits: list[str] = []
    for phrase, alias in FOOD_ALIASES.items():
        if phrase in q_norm:
            alias_hits.append(alias)

    def score(r):
        hashtag = str(r.get("hashtag_chinh") or "").lower().lstrip("#")
        _ht = r.get("hashtags_useful") or []
        hashtags_useful = " ".join(_ht if isinstance(_ht, list) else [str(_ht)]).lower()
        loc_str = str(r.get("location_search") or "").lower()
        name = str(r.get("tenquan_check") or r.get("tenquan") or "").lower()
        diachi = str(r.get("diachi_check") or r.get("diachi") or "").lower()
        mo_ta = str(r.get("review") or r.get("mo_ta") or "").lower()

        total = 0

        # 1. Alias match (cao nhất — chính xác loại món)
        for alias in alias_hits:
            if alias in hashtag:            total += 30
            if alias in hashtags_useful:    total += 20

        # 2. Full phrase match
        if q_norm in hashtag:               total += 25
        if q_norm in name:                  total += 20
        if q_norm in hashtags_useful:       total += 18
        if q_norm in mo_ta:                 total += 8

        # 3. Ngram match (bigram/trigram)
        for ng in ngrams:
            if ng in hashtag:               total += 18
            if ng in hashtags_useful:       total += 14
            if ng in name:                  total += 12
            if ng in mo_ta:                 total += 5

        # 4. Meaningful unigram match (bỏ stopword)
        for kw in meaningful_tokens:
            if kw in hashtag:               total += 10
            if kw in hashtags_useful:       total += 7
            if loc_str and kw in loc_str:   total += 6
            if kw in name:                  total += 5
            if kw in diachi:                total += 3
            if kw in mo_ta:                 total += 1

        return total

    scored = [(score(r), r) for r in all_records if match_location(r, location)]
    if not scored:
        scored = [(score(r), r) for r in all_records]

    scored.sort(key=lambda x: (
        -x[0],
        -(1 if x[1].get("diachi_match") else 0),
        -(1 if _is_recent(x[1]) else 0),
        -(x[1].get("rate") or 0)
    ))

    top = [r for s, r in scored if s > 0][:top_k]
    if not top:
        pool = [r for r in all_records if match_location(r, location)] or all_records
        top = sorted(
            pool,
            key=lambda r: (
                -(1 if r.get("diachi_match") else 0),
                -(1 if _is_recent(r) else 0),
                -(r.get("rate") or 0)
            )
        )[:top_k]
    return [enrich_record(dict(r)) for r in top]


@app.route("/quan/<video_id>")
def quan_detail(video_id):
    record = next((r for r in all_records if r.get("video_id") == video_id), None)
    if record is None:
        abort(404)
    r = enrich_record(dict(record))
    return render_template("quan_detail.html", r=r)


@app.route("/frames/<hashtag>/<video_id>")
def serve_frame(hashtag, video_id):
    path = get_frame_path(video_id, hashtag)
    if path and os.path.isfile(path):
        abs_path = os.path.abspath(path)
        return send_file(abs_path, mimetype="image/jpeg")
    abort(404)


@app.route("/frames/<hashtag>/<video_id>/<int:idx>")
def serve_frame_idx(hashtag, video_id, idx):
    """Serve the Nth frame (0-indexed) for slideshow."""
    folder = os.path.join(DEBUG_FRAMES_DIR, hashtag, video_id, "text_filtered")
    if not os.path.isdir(folder):
        folder = os.path.join(DEBUG_FRAMES_DIR, hashtag, video_id)
    if not os.path.isdir(folder):
        abort(404)
    frames = sorted(glob.glob(os.path.join(folder, "frame_*.jpg")))
    if not frames:
        frames = sorted(glob.glob(os.path.join(folder, "*.jpg")))
    if idx >= len(frames):
        abort(404)
    return send_file(os.path.abspath(frames[idx]), mimetype="image/jpeg")


@app.route("/")
def index():
    if "chat_history" not in session:
        session["chat_history"] = []
    location = request.args.get("loc", "").strip()
    seen_hashtags = set()
    top_results = []
    pool = [r for r in all_records if match_location(r, location)] or all_records
    sorted_records = sorted(
        pool,
        key=lambda r: (
            -(1 if r.get("diachi_match") else 0),
            -(1 if _is_recent(r) else 0),
            -(r.get("rate") or 0)
        )
    )
    for r in sorted_records:
        h = r.get("hashtag_chinh", "")
        if h not in seen_hashtags:
            seen_hashtags.add(h)
            top_results.append(enrich_record(dict(r)))
        if len(top_results) >= 25:
            break
    return render_template("index.html",
                           chat_history=session["chat_history"],
                           top_results=top_results,
                           location=location)


@app.route("/search")
def search():
    if "chat_history" not in session:
        session["chat_history"] = []
    query = request.args.get("q", "").strip()
    location = request.args.get("loc", "").strip()
    results = search_restaurants(query, location=location)
    return render_template("index.html",
                           chat_history=session["chat_history"],
                           query=query,
                           location=location,
                           results=results)


@app.route("/chat_ajax", methods=["POST"])
def chat_ajax():
    data = request.get_json()
    user_input = data.get("user_input", "").strip()
    if not user_input:
        return jsonify({"response": ""})
    if "chat_history" not in session:
        session["chat_history"] = []
    response = generate_response(user_input)
    session["chat_history"].append(("user", user_input))
    session["chat_history"].append(("bot", response))
    session.modified = True
    return jsonify({"response": response})


@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.form["user_input"]
    response = generate_response(user_input)
    session["chat_history"].append(("user", user_input))
    session["chat_history"].append(("bot", response))
    session.modified = True
    sorted_records = sorted(
        all_records,
        key=lambda r: (
            -(1 if r.get("diachi_match") else 0),
            -(1 if _is_recent(r) else 0),
            -(r.get("rate") or 0)
        )
    )
    top_results = [enrich_record(dict(r)) for r in sorted_records[:20]]
    return render_template("index.html",
                           chat_history=session["chat_history"],
                           top_results=top_results)


@app.route("/search_json")
def search_json():
    query = request.args.get("q", "").strip()
    location = request.args.get("loc", "").strip()
    limit = min(int(request.args.get("limit", 10)), 30)
    results = search_restaurants(query, top_k=30, location=location)
    if len(results) > 3:
        top3 = results[:3]
        rest = results[3:]
        random.shuffle(rest)
        results = top3 + rest
    return jsonify(results[:limit])


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)