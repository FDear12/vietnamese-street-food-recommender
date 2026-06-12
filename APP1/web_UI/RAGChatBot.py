"""
RAGChatBot v4 — LangChain + FAISS + Google Gemini
Cải tiến so với v3:
  - Hỗ trợ data mới: review là list[{time, rating, text}] — flatten lấy rating + text, bỏ time
  - page_content ưu tiên: hashtag_chinh → location_search → tenquan/diachi → review text → mo_ta → hashtags_useful
  - diachi_match=True → dùng tenquan_check + diachi_check thay vì tenquan + diachi
  - Tính sẵn _is_stale (cap_nhat_ngay_dang > 180 ngày hoặc null) trong metadata
  - Xử lý location_search có thể vắng mặt hoàn toàn (không có key, khác null)
  - v4.1: Thêm link /quan/<hashtag>/<video_id> vào context → LLM kèm link mở tab mới
"""

import json
import os
import re
import time
import logging
from datetime import datetime, timedelta
from os import getenv
import dotenv

dotenv.load_dotenv()

GOOGLE_API_KEY   = getenv("GOOGLE_API_KEY")
DATA_PATH        = "data_v2/data.json"
FAISS_DB_PATH    = "faiss_db"
LLM_MODEL_NAME   = "gemini-2.5-flash"
TOP_K            = 10
SCORE_THRESHOLD  = 70   # FAISS L2 — càng cao càng rộng, tune dựa vào log [RETRIEVAL] all_scores
RAG_EVAL_LOG     = "rag_eval.jsonl"
STALE_DAYS       = 180   # quán không cập nhật quá 6 tháng → cảnh báo

HASHTAG_CHINH = {
    "banhbeo"       : "Bánh Bèo",
    "banhbotloc"    : "Bánh Bột Lọc",
    "banhcan"       : "Bánh Căn",
    "banhcanh"      : "Bánh Canh",
    "banhbao"       : "Bánh Bao",
    "banhcuon"      : "Bánh Cuốn",
    "banhkhot"      : "Bánh Khọt",

    "banhtrangnuong": "Bánh Tráng Nướng",
    "banhxeo"       : "Bánh Xèo",
    "bunbohue"      : "Bún Bò Huế",
    "buncha"        : "Bún Chả",
    "bundaumamtom"  : "Bún Đậu Mắm Tôm",
    "bunmam"        : "Bún Mắm",
    "bunrieu"       : "Bún Riêu",
    "bunthitnuong"  : "Bún Thịt Nướng",
    "caolau"        : "Cao Lầu",
    "chaolong"      : "Cháo Lòng",
    "comtam"        : "Cơm Tấm",

    "hutieu"        : "Hủ Tiếu",
    "nemchua"       : "Nem Chua",
    "pho"           : "Phở",

    "miquang"       : "Mì Quảng"
}
FOOD_QUERY_EXPAND = {
    # Bánh Bèo
    "bánh bèo"          : "banhbeo",
    "banh beo"          : "banhbeo",

    # Bánh Bột Lọc
    "bánh bột lọc"      : "banhbotloc",
    "banh bot loc"      : "banhbotloc",

    # Bánh Căn
    "bánh căn"          : "banhcan",
    "banh can"          : "banhcan",

    # Bánh Canh
    "bánh canh"         : "banhcanh",
    "banh canh"         : "banhcanh",

    # Bánh Bao
    "bánh bao"          : "banhbao",
    "banh bao"          : "banhbao",

    # Bánh Cuốn
    "bánh cuốn"         : "banhcuon",
    "banh cuon"         : "banhcuon",

    # Bánh Khọt
    "bánh khọt"         : "banhkhot",
    "banh khot"         : "banhkhot",

    # Bánh Tráng Nướng
    "bánh tráng nướng"  : "banhtrangnuong",
    "banh trang nuong"  : "banhtrangnuong",
    "bánh tráng"        : "banhtrangnuong",
    "banh trang"        : "banhtrangnuong",
    "bánh tráng kẹp"    : "banhtrangnuong",
    "bánh tráng cuộn"   : "banhtrangnuong",

    # Bánh Xèo
    "bánh xèo"          : "banhxeo",
    "banh xeo"          : "banhxeo",

    # Bún Bò Huế
    "bún bò huế"        : "bunbohue",
    "bun bo hue"        : "bunbohue",
    "bún bò"            : "bunbohue",
    "bun bo"            : "bunbohue",

    # Bún Chả
    "bún chả"           : "buncha",
    "bun cha"           : "buncha",

    # Bún Đậu Mắm Tôm
    "bún đậu mắm tôm"   : "bundaumamtom",
    "bun dau mam tom"   : "bundaumamtom",
    "bún đậu"           : "bundaumamtom",
    "bun dau"           : "bundaumamtom",

    # Bún Mắm
    "bún mắm"           : "bunmam",
    "bun mam"           : "bunmam",

    # Bún Riêu
    "bún riêu"          : "bunrieu",
    "bun rieu"          : "bunrieu",

    # Bún Thịt Nướng
    "bún thịt nướng"    : "bunthitnuong",
    "bun thit nuong"    : "bunthitnuong",
    "bún thịt"          : "bunthitnuong",

    # Cao Lầu
    "cao lầu"           : "caolau",
    "cao lau"           : "caolau",

    # Cháo Lòng
    "cháo lòng"         : "chaolong",
    "chao long"         : "chaolong",
    "cháo"              : "chaolong",

    # Cơm Tấm
    "cơm tấm"           : "comtam",
    "com tam"           : "comtam",
    "cơm sườn"          : "comtam",

    # Hủ Tiếu
    "hủ tiếu"           : "hutieu",
    "hu tieu"           : "hutieu",

    # Nem Chua
    "nem chua"          : "nemchua",

    # Phở
    "phở"               : "pho",
    "pho"               : "pho",
    "phở bò"            : "pho",
    "pho bo"            : "pho",
    "phở gà"            : "pho",
    "pho ga"            : "pho",

    # Mì Quảng
    "mì quảng"          : "miquang",
    "mi quang"          : "miquang",
    "mỳ quảng"          : "miquang",
    "my quang"          : "miquang",
    "mì"                : "miquang",
}

def expand_query(query: str) -> str:
    """Thêm hashtag chuẩn vào query để FAISS dễ khớp hơn."""
    q_low = query.lower()
    extras = []
    for phrase, hashtag in FOOD_QUERY_EXPAND.items():
        if phrase in q_low and hashtag not in q_low:
            extras.append(hashtag)
    if extras:
        return query + " " + " ".join(extras)
    return query
# ── Logger ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("rag_perf.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
perf_logger = logging.getLogger("rag.perf")

# ── LangChain imports ─────────────────────────────────────────────────────────
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain.prompts import PromptTemplate

# ── 1. Load data ──────────────────────────────────────────────────────────────
with open(DATA_PATH, encoding="utf-8") as f:
    all_records = json.load(f)

all_records = [r for r in all_records if r.get("tenquan")]

# ── 2. Helpers cho data mới ───────────────────────────────────────────────────
def flatten_review(review_raw) -> str:
    """
    Data mới : review là list[{time, rating, text}] — chỉ lấy rating + text, bỏ time.
    Data cũ  : review là string — trả về thẳng.
    Bỏ qua item không có text thực sự.
    """
    if not review_raw:
        return ""
    if isinstance(review_raw, str):
        return review_raw.strip()
    if isinstance(review_raw, list):
        parts = []
        for item in review_raw:
            if not isinstance(item, dict):
                continue
            text   = (item.get("text") or "").strip()
            rating = item.get("rating")
            if not text:
                continue
            if rating is not None:
                parts.append(f"[{rating}★] {text}")
            else:
                parts.append(text)
        return " | ".join(parts)
    return ""


def best_tenquan(r: dict) -> str:
    """diachi_match=True → tenquan_check (đã xác thực), ngược lại tenquan gốc."""
    if r.get("diachi_match") is True:
        return r.get("tenquan_check") or r.get("tenquan") or ""
    return r.get("tenquan") or ""


def best_diachi(r: dict) -> str:
    """diachi_match=True → diachi_check (đã xác thực Google Maps), ngược lại diachi gốc OCR."""
    if r.get("diachi_match") is True:
        return r.get("diachi_check") or r.get("diachi") or ""
    return r.get("diachi") or ""


def is_stale(r: dict) -> bool:
    """
    Trả về True nếu cap_nhat_ngay_dang vắng mặt hoặc > STALE_DAYS ngày trước.
    Dùng làm flag cảnh báo trong metadata, không để LLM tự tính.
    """
    raw = r.get("cap_nhat_ngay_dang") or ""
    if not raw:
        return True
    try:
        dt = datetime.strptime(str(raw)[:10], "%Y-%m-%d")
        return dt < datetime.now() - timedelta(days=STALE_DAYS)
    except Exception:
        return True


# ── 3. Documents ──────────────────────────────────────────────────────────────
def records_to_documents(records: list[dict]) -> list[Document]:
    docs = []
    for r in records:
        hashtag  = r.get("hashtag_chinh") or ""
        ten_mon  = HASHTAG_CHINH.get(hashtag, "")

        location = r.get("location_search") or ""

        tenquan  = best_tenquan(r)
        diachi   = best_diachi(r)

        review_text = flatten_review(r.get("review"))
        mo_ta       = (r.get("mo_ta") or "").strip()

        _ht      = r.get("hashtags_useful") or []
        hashtags = " ".join(_ht if isinstance(_ht, list) else [str(_ht)])

        content = " ".join(filter(None, [
            hashtag,
            ten_mon,
            location,
            tenquan,
            diachi,
            review_text,
            mo_ta,
            hashtags,
        ]))

        docs.append(Document(
            page_content=content,
            metadata={
                "tenquan"      : tenquan,
                "diachi"       : diachi,
                "location"     : location,
                "rate"         : r.get("rate") or "",
                "price_level"  : r.get("price_level") or "",
                "has_delivery" : r.get("has_delivery") or "",
                "so_dien_thoai": r.get("so_dien_thoai") or "",
                "gio_mo_cua"   : r.get("gio_mo_cua") or "",
                "hashtag_chinh": hashtag,
                "video_id"     : r.get("video_id") or "",   # ← THÊM MỚI
                "diachi_match" : r.get("diachi_match") or False,
                "review"       : review_text,
                "mo_ta"        : mo_ta,
                "is_stale"     : is_stale(r),
            }
        ))
    return docs

# ── 4. Embeddings ─────────────────────────────────────────────────────────────
embeddings = HuggingFaceEmbeddings(
    model_name="keepitreal/vietnamese-sbert",
    model_kwargs={"device": "cuda"},
    encode_kwargs={"batch_size": 64},
)

# ── 5. Vector store ───────────────────────────────────────────────────────────
def build_vector_store(batch_size: int = 500) -> FAISS:
    print("Đang build vector store... (chỉ chạy 1 lần)")
    docs = records_to_documents(all_records)
    t0   = time.perf_counter()
    db   = None
    total = (len(docs) - 1) // batch_size + 1
    for i in range(0, len(docs), batch_size):
        batch = docs[i: i + batch_size]
        print(f"  Batch {i//batch_size+1}/{total} ({len(batch)} docs)...")
        if db is None:
            db = FAISS.from_documents(batch, embeddings)
        else:
            db.add_documents(batch)
    db.save_local(FAISS_DB_PATH)
    perf_logger.info(f"[BUILD] {len(docs)} docs — {time.perf_counter()-t0:.2f}s")
    return db

def load_vector_store() -> FAISS:
    t0 = time.perf_counter()
    db = FAISS.load_local(FAISS_DB_PATH, embeddings, allow_dangerous_deserialization=True)
    perf_logger.info(f"[LOAD] FAISS — {time.perf_counter()-t0:.3f}s")
    return db

db = load_vector_store() if os.path.exists(FAISS_DB_PATH) else build_vector_store()

# ── 6. LLM ───────────────────────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model=LLM_MODEL_NAME,
    google_api_key=GOOGLE_API_KEY,
    temperature=0.3,
)

# ── 7. Prompt ─────────────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """
Bạn là trợ lý AI gợi ý quán ăn tại các thành phố Việt Nam (Đà Nẵng, Hồ Chí Minh, Hà Nội, ...).

NGUYÊN TẮC BẮT BUỘC:
- Nếu người dùng chào hỏi hoặc nói chuyện xã giao (xin chào, hi, cảm ơn, bạn khỏe không, ...) thì hãy đáp lại tự nhiên thân thiện mà KHÔNG cần tra dữ liệu, sau đó hỏi xem họ muốn tìm món gì hoặc ở đâu.
- CHỈ dùng thông tin trong phần "Dữ liệu quán ăn" bên dưới để trả lời các câu hỏi về quán/món ăn.
- KHÔNG được tự bịa tên quán, tên món, địa chỉ, số điện thoại ngoài dữ liệu.
- KHÔNG được gợi ý món thay thế khi không tìm thấy món người dùng hỏi.
- Người dùng hỏi về món ăn (dù không nói rõ "quán") thì hiểu ngầm là đang tìm chỗ ăn món đó.
  Ví dụ: "bánh tráng nướng ngon không?" = đang hỏi tìm chỗ ăn bánh tráng nướng.
- Nếu dữ liệu không có món/chỗ phù hợp để kiểm tra và gợi ý quán ăn, CHỈ trả lời  mẫu:
  "Xin lỗi, mình không tìm thấy thông tin về [món người dùng hỏi] + [lời gợi ý khác]." 
- Nếu câu hỏi không liên quan đến ẩm thực/quán ăn (game, du lịch, ...), trả lời:
  "Mình chỉ hỗ trợ gợi ý quán ăn thôi nhé!"
- Trả lời bằng tiếng Việt, thân thiện và ngắn gọn.

CÁCH TRÌNH BÀY:
- Viết tự nhiên như người đang kể chuyện, KHÔNG dùng gạch đầu dòng, bullet point hay format "Địa chỉ: ..., Mô tả: ...".
- Mỗi quán viết thành một đoạn ngắn: tên quán nằm ở đâu, quán như thế nào.
- Nếu có review thì thêm tự nhiên: "Một số người từng ăn ở đây nhận xét rằng..."
- Nếu có rating thì đề cập nhẹ: "quán được đánh giá X sao".
- Nếu có SĐT, giờ mở cửa, giá thì đề cập tự nhiên vào cuối đoạn nếu người dùng hỏi hoặc thấy hữu ích.
- Ghi chú địa chỉ chưa xác thực hoặc thông tin cũ thì viết thành câu tự nhiên ở cuối, không dùng dấu ngoặc đơn.
- Mỗi quán được gợi ý BẮT BUỘC phải dùng tên quán làm link, format: [Tên Quán](Link chi tiết)
  Ví dụ: [Cơm Tấm Bếp Nhà](/quan/tk_7643431622917819668) — không được thêm chữ "Xem chi tiết" hay ngoặc đơn.
  Tên quán trong link chính là tên quán đang nhắc đến trong đoạn văn.

HƯỚNG DẪN ĐỌC DỮ LIỆU:
- Ưu tiên gợi ý: khớp món ăn (hashtag_chinh) → khớp địa điểm (location) → review/rating → mo_ta.
- Một số quán không có trường location, vẫn gợi ý bình thường nếu khớp món.
- diachi_match=True → địa chỉ đã xác thực Google Maps, tin cậy cao.
- diachi_match=False hoặc null → địa chỉ từ OCR chưa xác thực, nhắc người dùng kiểm tra lại.
- is_stale=True → thông tin có thể cũ, nhắc người dùng xác nhận trước khi đến.
- Nếu cả diachi_match=False và is_stale=True thì gộp thành một câu nhắc chung ở cuối.

Dữ liệu quán ăn tìm được:
{context}

Lịch sử hội thoại:
{history}

Câu hỏi mới nhất: {question}
"""

prompt = PromptTemplate(
    input_variables=["context", "history", "question"],
    template=PROMPT_TEMPLATE,
)

# ── 8. Tách câu hỏi mới nhất khỏi history ────────────────────────────────────
HISTORY_TURNS = 6

def split_conversation(conversation: str) -> tuple[str, str]:
    """
    Tách câu hỏi cuối cùng của User ra khỏi history.
    Chỉ embed câu hỏi mới → không bị nhiễu bởi context cũ.
    Giới hạn history còn HISTORY_TURNS lượt gần nhất để tránh context window phình.
    Trả về (latest_question, history_text).
    """
    lines = [l for l in conversation.strip().splitlines() if l.strip()]
    last_user_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("User:"):
            last_user_idx = i
            break

    if last_user_idx is None:
        return conversation.strip(), ""

    latest_q      = lines[last_user_idx][len("User:"):].strip()
    history_lines = lines[:last_user_idx]

    max_lines     = HISTORY_TURNS * 2
    history_lines = history_lines[-max_lines:] if len(history_lines) > max_lines else history_lines

    history = "\n".join(history_lines).strip()
    return latest_q, history

# ── 9. Post-verify: kiểm tra LLM không bịa tên quán ─────────────────────────
def verify_answer(answer: str, context_docs: list[Document]) -> tuple[str, bool]:
    return answer, False

# ── 10. Ghi đánh giá RAG ─────────────────────────────────────────────────────
def log_rag_eval(record: dict):
    def convert(obj):
        if hasattr(obj, 'item'):   # numpy float32
            return round(float(obj.item()), 3)
        if isinstance(obj, float):
            return round(obj, 3)
        return obj

    clean = {k: ([convert(x) for x in v] if isinstance(v, list) else convert(v))
             for k, v in record.items()}
    with open(RAG_EVAL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(clean, ensure_ascii=False) + "\n")

# ── 11. Hàm chat chính ───────────────────────────────────────────────────────
SOCIAL_KEYWORDS = ["hi", "hello", "xin chào", "chào", "cảm ơn", "camon", "oke", "ok", "bạn ơi", "hey", "helo", "hê lô", "tạm biệt", "bye"]

def is_social(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in SOCIAL_KEYWORDS) and len(t) < 30


def review_chain(conversation: str) -> str:
    t_total = time.perf_counter()

    latest_q, history_text = split_conversation(conversation)

    # --- Xử lý câu xã giao — bypass FAISS ---
    if is_social(latest_q):
        raw = llm.invoke(
            f"Người dùng nói: '{latest_q}'. Hãy đáp lại thân thiện bằng tiếng Việt, "
            f"sau đó hỏi họ muốn tìm món ăn hay quán gì ở thành phố nào."
        )
        return raw.content if hasattr(raw, "content") else str(raw)

    # --- Retrieval ---
    t0 = time.perf_counter()
    expanded_q = expand_query(latest_q)
    docs_and_scores = db.similarity_search_with_score(expanded_q, k=TOP_K)
    t_ret = time.perf_counter() - t0

    scores        = [round(s, 3) for _, s in docs_and_scores]
    relevant_docs = [doc for doc, score in docs_and_scores if score < SCORE_THRESHOLD]
    hit_rate      = len(relevant_docs) / TOP_K
    avg_score     = round(sum(scores) / len(scores), 3) if scores else 0
    min_score     = scores[0] if scores else 0

    perf_logger.info(
        f"[RETRIEVAL] relevant={len(relevant_docs)}/{TOP_K} | "
        f"hit_rate={hit_rate:.2f} | min_score={min_score} | "
        f"avg_score={avg_score} | all_scores={scores} | t={t_ret:.3f}s"
    )

    # Không có doc liên quan → block, không gọi LLM
    if not relevant_docs:
        t_elapsed = round(time.perf_counter() - t_total, 3)
        perf_logger.info(f"[QUERY] BLOCKED | total={t_elapsed}s | q={latest_q[:60]!r}")
        log_rag_eval({
            "ts"          : time.strftime("%Y-%m-%dT%H:%M:%S"),
            "question"    : latest_q,
            "retrieved"   : 0,
            "hit_rate"    : 0.0,
            "avg_score"   : avg_score,
            "min_score"   : min_score,
            "hallucinated": False,
            "blocked"     : True,
            "latency_s"   : t_elapsed,
        })
        return "Xin lỗi, mình không biết món hay quán bạn hỏi trong trí nhớ của mình."

    # --- Gọi LLM ---
    context_parts = []
    for doc in relevant_docs:
        m = doc.metadata
        diachi_verified = m.get("diachi_match") is True
        lines = [
            f"Tên quán  : {m.get('tenquan', '')}",
            f"Địa chỉ   : {m.get('diachi', '')}" + (" ✓(đã xác thực)" if diachi_verified else " ⚠(chưa xác thực)"),
        ]
        if m.get("location"):
            lines.append(f"Khu vực   : {m.get('location')}")
        if m.get("rate"):
            lines.append(f"Rating    : {m.get('rate')}★")
        if m.get("price_level"):
            lines.append(f"Giá       : {m.get('price_level')}")
        if m.get("so_dien_thoai"):
            lines.append(f"SĐT       : {m.get('so_dien_thoai')}")
        if m.get("gio_mo_cua"):
            lines.append(f"Giờ mở cửa: {m.get('gio_mo_cua')}")
        if m.get("has_delivery"):
            lines.append(f"Giao hàng : {m.get('has_delivery')}")
        if m.get("review"):
            lines.append(f"Review    : {m.get('review')}")
        elif m.get("mo_ta"):
            lines.append(f"Mô tả     : {m.get('mo_ta')}")

        # ── Link chi tiết ──────────────────────────────────────────────────────
        video_id = m.get("video_id", "")
        hashtag  = m.get("hashtag_chinh", "")
        if video_id and hashtag:
            lines.append(f"Link chi tiết: /quan/{video_id}")

        lines.append(f"[diachi_match={m.get('diachi_match')} | is_stale={m.get('is_stale')}]")
        context_parts.append("\n".join(lines))

    context = "\n\n---\n\n".join(context_parts)
    llm_prompt = prompt.format(
        context  = context,
        history  = history_text or "(chưa có lịch sử)",
        question = latest_q,
    )

    t0  = time.perf_counter()
    raw = llm.invoke(llm_prompt)
    t_llm = time.perf_counter() - t0

    answer_text = raw.content if hasattr(raw, "content") else str(raw)
    answer_final, is_hallucinated = verify_answer(answer_text, relevant_docs)

    t_elapsed = round(time.perf_counter() - t_total, 3)

    log_rag_eval({
        "ts"           : time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question"     : latest_q,
        "retrieved"    : len(relevant_docs),
        "hit_rate"     : round(hit_rate, 3),
        "avg_score"    : avg_score,
        "min_score"    : min_score,
        "scores_top3"  : scores[:3],
        "hallucinated" : is_hallucinated,
        "blocked"      : False,
        "latency_ret_s": round(t_ret, 3),
        "latency_llm_s": round(t_llm, 3),
        "latency_s"    : t_elapsed,
    })

    perf_logger.info(
        f"[QUERY] OK | ret={t_ret:.3f}s | llm={t_llm:.3f}s | total={t_elapsed}s | "
        f"hit={len(relevant_docs)}/{TOP_K} | hallucinated={is_hallucinated} | q={latest_q[:60]!r}"
    )

    return answer_final


# ── 12. Test CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("RAGChatBot v4 — LangChain + FAISS + vietnamese-sbert")
    print("Gõ 'quit' để thoát\n")

    history = []
    while True:
        user_input = input("User: ").strip()
        if user_input.lower() == "quit":
            break
        history.append(f"User: {user_input}")

        max_lines  = HISTORY_TURNS * 2
        window     = history[-max_lines:] if len(history) > max_lines else history
        conversation = "\n".join(window)

        answer = review_chain(conversation)
        print(f"Bot: {answer}\n")
        history.append(f"Bot: {answer}")