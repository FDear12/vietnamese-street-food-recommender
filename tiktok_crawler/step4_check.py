# step4_check.py
import json
import asyncio
import re
import unicodedata
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from config import HASHTAG_CHINH

# ─── CONFIG ───────────────────────────────────────────
INPUT_FILE    = "data_noncheck.json"
OUTPUT_FILE   = "data.json"
NUM_WORKERS   = 2
DELAY_BETWEEN = 2

HASHTAG_TEN = {k: v for k, v in HASHTAG_CHINH.items()}

WARM_QUERIES = [
    "thời tiết hôm nay",
    "tin tức mới nhất",
    "món ăn ngon",
    "quán cà phê đà nẵng",
    "du lịch việt nam",
    "ẩm thực đường phố",
]

# ─── GLOBALS ──────────────────────────────────────────
file_lock    = asyncio.Lock()
captcha_lock = asyncio.Lock()
warm_pages: list = []   # 6 tab warm-up, dùng lại khi captcha

# ─── HELPER ───────────────────────────────────────────

def load_data(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

async def save_data(records: list, path: str):
    async with file_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

def is_within_days(date_str: str, days: int) -> bool:
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        return datetime.now() - date <= timedelta(days=days)
    except:
        return False

def calc_cap_nhat(ngay_dang: str) -> str:
    if ngay_dang == "unknown":
        return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if is_within_days(ngay_dang, 30):
        return ngay_dang
    return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

def build_keyword(record: dict) -> str:
    hashtag  = record.get("hashtag_chinh", "")
    ten_mon  = HASHTAG_TEN.get(hashtag, hashtag)
    diachi   = record.get("diachi", "")
    location = record.get("location_search")
    if location:
        return f"Quán {ten_mon} {diachi} {location}"
    return f"Quán {ten_mon} {diachi}"

def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text.strip()

def extract_addr_key(diachi: str) -> str:
    part = diachi.split(",")[0].strip()
    m = re.search(r"\d", part)
    if m:
        part = part[m.start():]
    part = re.sub(r"[^a-zA-Z0-9\u00C0-\u024F\u1E00-\u1EFF\s]", " ", part)
    part = normalize_text(part)
    part = re.sub(r"\s+", " ", part).strip()
    return part[:15]

def similarity_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    set_a, set_b = set(a.replace(" ", "")), set(b.replace(" ", ""))
    common = len(set_a & set_b)
    return common / max(len(set_a), len(set_b))

def parse_cap_nhat_from_review(time_text: str) -> str:
    t = time_text.lower().strip()
    today = datetime.now()
    if re.search(r"vài giây|giây trước|vài phút|phút trước|vài giờ|giờ trước", t):
        return today.strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*(giây|phút|giờ)", t)
    if m:
        return today.strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*ngày", t)
    if m:
        return (today - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*tuần", t)
    if m:
        return (today - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m-%d")
    if re.search(r"1\s*tháng", t):
        return (today - timedelta(days=30)).strftime("%Y-%m-%d")
    return today.strftime("%Y-%m-%d")

def parse_review_age(text: str) -> bool:
    t = text.lower().strip()
    if re.search(r"vài giây|giây trước|vài phút|phút trước|vài giờ|giờ trước", t):
        return True
    m = re.search(r"(\d+)\s*(giây|phút|giờ)", t)
    if m:
        return True
    m = re.search(r"(\d+)\s*ngày", t)
    if m:
        return int(m.group(1)) <= 30
    m = re.search(r"(\d+)\s*tuần", t)
    if m:
        return int(m.group(1)) <= 4
    if re.search(r"1\s*tháng", t):
        return True
    return False

# ─── CAPTCHA ──────────────────────────────────────────

async def reload_warm_pages(context):
    """Reload 3 tab đầu trong warm_pages sau khi giải captcha."""
    print("🔄 Reload 3 tab warm-up đầu...")
    for i in range(min(3, len(warm_pages))):
        try:
            url = f"https://www.google.com/search?q={WARM_QUERIES[i]}&hl=vi"
            await warm_pages[i].goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)
            print(f"   ✓ Warm tab {i+1} reloaded")
        except Exception as e:
            print(f"   ⚠️ Warm tab {i+1} lỗi: {e}")

async def check_captcha(page, worker_id: int, current_url: str, context) -> bool:
    """
    Kiểm tra captcha bằng cách tìm a#logo.
    Nếu không có → dừng, chờ input(), reload 3 warm tab đầu, rồi goto lại current_url.
    Dùng captcha_lock để chỉ 1 worker xử lý tại 1 thời điểm.
    """
    try:
        logo = await page.query_selector("a#logo")
        if logo:
            return False
    except:
        return False

    print(f"\n[W{worker_id}] 🚨 CAPTCHA detected!")

    async with captcha_lock:
        # Check lại sau khi có lock — worker khác có thể đã xử lý
        try:
            logo = await page.query_selector("a#logo")
            if logo:
                print(f"[W{worker_id}] ✅ Captcha đã xử lý, goto lại...")
                await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                return True
        except:
            pass

        # Chờ người dùng giải captcha
        print("=" * 50)
        await asyncio.get_event_loop().run_in_executor(
            None, input, "⏳ Giải captcha xong nhấn Enter..."
        )
        print("=" * 50 + "\n")

        # Reload 3 warm tab đầu để làm nóng lại session
        await reload_warm_pages(context)

    # Goto lại URL hiện tại
    await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    return True

# ─── HELPER PLAYWRIGHT ────────────────────────────────

NULL_CHECK = {
    "tenquan_check": None,
    "diachi_check" : None,
    "diachi_match" : None,
    "rate"         : None,
    "price_level"  : None,
    "has_delivery" : None,
    "so_dien_thoai": None,
    "gio_mo_cua"   : None,
    "review"       : None,
}

async def safe_text(el) -> str | None:
    try:
        t = (await el.inner_text()).strip()
        return t if t else None
    except:
        return None

async def safe_attr(el, attr: str) -> str | None:
    try:
        return await el.get_attribute(attr)
    except:
        return None

# ─── CHECK 1 RECORD ───────────────────────────────────

async def check_record(context, record: dict, worker_id: int) -> dict:
    video_id  = record.get("video_id", "?")
    ngay_dang = record.get("ngay_dang", "unknown")

    cap_nhat   = calc_cap_nhat(ngay_dang)
    record["cap_nhat_ngay_dang"] = cap_nhat

    keyword    = build_keyword(record)
    search_url = f"https://www.google.com/search?q={keyword}&hl=vi"
    print(f"\n[W{worker_id}] 🔍 {video_id} | {keyword}")

    page = await context.new_page()
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await check_captcha(page, worker_id, search_url, context)

        # ── Kiểm tra Knowledge Panel ──────────────────
        rhs = await page.query_selector("div#rhs")
        if not rhs:
            rhs = await page.query_selector("div.TQc1id")
        if not rhs:
            print(f"[W{worker_id}]   ⚠️ Không có Knowledge Panel → null")
            record.update({**NULL_CHECK, "cap_nhat_ngay_dang": ngay_dang})
            return record

        title_el = await rhs.query_selector("div[data-attrid='title']")
        if not title_el:
            print(f"[W{worker_id}]   ⚠️ Không có title trong KP → null")
            record.update({**NULL_CHECK, "cap_nhat_ngay_dang": ngay_dang})
            return record

        # ── Địa chỉ Google ───────────────────────────
        diachi_google = None
        addr_block = await rhs.query_selector("[data-attrid='kc:/location/location:address']")
        if addr_block:
            lrz = await addr_block.query_selector("span.LrzXr")
            if lrz:
                diachi_google = await safe_text(lrz)
        if not diachi_google:
            lrz = await rhs.query_selector("span.LrzXr")
            if lrz:
                diachi_google = await safe_text(lrz)

        # ── So sánh địa chỉ ──────────────────────────
        diachi_data  = record.get("diachi", "")
        diachi_match = None

        if diachi_google and diachi_data:
            key_google = extract_addr_key(diachi_google)
            key_data   = extract_addr_key(diachi_data)
            ratio = similarity_ratio(key_google, key_data)
            diachi_match = ratio >= 0.9
            print(f"[W{worker_id}]   📍 match={diachi_match} ({ratio:.2f}) | data='{key_data}' | google='{key_google}'")
        else:
            print(f"[W{worker_id}]   ⚠️ Thiếu địa chỉ để so sánh")

        if not diachi_match:
            print(f"[W{worker_id}]   ✗ Không khớp địa chỉ → null, cap_nhat=ngay_dang")
            record.update({**NULL_CHECK, "diachi_match": diachi_match, "cap_nhat_ngay_dang": ngay_dang})
            return record

        # ── tenquan_check ─────────────────────────────
        tenquan_check = None
        title_inner = await rhs.query_selector("div.DoxwDb div[data-attrid='title'], div[data-attrid='title'] span")
        if not title_inner:
            title_inner = title_el
        tenquan_check = await safe_text(title_inner)

        # ── diachi_check ──────────────────────────────
        diachi_check = diachi_google

        # ── rate ──────────────────────────────────────
        rate = None
        rate_el = await rhs.query_selector("span.Aq14fc[aria-hidden='true']")
        if rate_el:
            rate_raw = await safe_text(rate_el)
            if rate_raw:
                try:
                    rate = float(rate_raw.replace(",", "."))
                except:
                    pass

        # ── price_level ───────────────────────────────
        price_level = None
        price_block = await rhs.query_selector("[data-attrid='kc:/local:concrete_price_range']")
        if price_block:
            parent = await price_block.query_selector("div.Neccf")
            if parent:
                full = await safe_text(parent)
                if full:
                    price_level = re.sub(r"Giá mỗi người\s*:\s*", "", full).split("\n")[0].strip()

        # ── has_delivery ──────────────────────────────
        has_delivery = False
        rhs_text = await safe_text(rhs) or ""
        if any(x in rhs_text.lower() for x in ["giao hàng", "delivery", "giao tận nơi"]):
            has_delivery = True

        # ── so_dien_thoai ─────────────────────────────
        so_dien_thoai = None
        phone_block = await rhs.query_selector("[data-attrid='kc:/local:alt phone'], [data-attrid*='phone']")
        if phone_block:
            phone_span = await phone_block.query_selector("span[aria-label*='Gọi đến số']")
            if phone_span:
                so_dien_thoai = await safe_text(phone_span)
            else:
                lrz2 = await phone_block.query_selector("span.LrzXr")
                if lrz2:
                    so_dien_thoai = await safe_text(lrz2)

        # ── gio_mo_cua ────────────────────────────────
        gio_mo_cua = None
        hours_block = await rhs.query_selector("[data-attrid='kc:/location/location:hours']")
        if hours_block:
            status_el = await hours_block.query_selector("span.JjSWRd")
            if status_el:
                gio_mo_cua = await safe_text(status_el)
            if not gio_mo_cua:
                table_el = await hours_block.query_selector("table.WgFkxc")
                if table_el:
                    gio_mo_cua = await safe_text(table_el)

        print(f"[W{worker_id}]   ✓ ten='{tenquan_check}' | rate={rate} | phone={so_dien_thoai}")

        # ── Bước 4: Tab Bài đánh giá ──────────────────
        reviews     = None
        review_link = None
        try:
            links = await page.query_selector_all("a.n1obkb")
            for link in links:
                span = await link.query_selector("span.aSAiSd")
                if span:
                    txt = (await safe_text(span) or "").lower()
                    if "đánh giá" in txt:
                        review_link = await safe_attr(link, "href")
                        if review_link and not review_link.startswith("http"):
                            review_link = "https://www.google.com" + review_link
                        break
        except Exception as e:
            print(f"[W{worker_id}]   ⚠️ Lỗi tìm nút đánh giá: {e}")

        if review_link:
            tab2 = await context.new_page()
            try:
                await tab2.goto(review_link, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                await check_captcha(tab2, worker_id, review_link, context)

                # Click tab "Mới nhất"
                try:
                    newest = await tab2.query_selector("div[data-sort='2']")
                    if newest:
                        await newest.click()
                        await asyncio.sleep(2)
                        print(f"[W{worker_id}]   → Đã click Mới nhất")
                except Exception as e:
                    print(f"[W{worker_id}]   ⚠️ Lỗi click Mới nhất: {e}")

                # Lấy review
                review_items = await tab2.query_selector_all("div.bwb7ce[jsname='ShBeI']")
                reviews = []
                for item in review_items:
                    if len(reviews) >= 5:
                        break
                    try:
                        time_el   = await item.query_selector("span.y3Ibjb")
                        time_text = await safe_text(time_el) if time_el else None
                        if not time_text or not parse_review_age(time_text):
                            continue

                        # Click "Xem thêm" nếu có
                        try:
                            xem_them = await item.query_selector("button.w8nwRe, span.w8nwRe")
                            if xem_them:
                                await xem_them.click()
                                await asyncio.sleep(0.5)
                        except:
                            pass

                        text_el     = await item.query_selector("div.OA1nbd")
                        review_text = None
                        if text_el:
                            raw = await safe_text(text_el) or ""
                            raw = re.sub(r"…\s*Xem thêm", "", raw)
                            raw = raw.replace("\n", " ").strip()
                            review_text = raw if raw else None

                        rating_val = None
                        rating_el  = await item.query_selector("div.dHX2k")
                        if rating_el:
                            aria = await safe_attr(rating_el, "aria-label") or ""
                            m = re.search(r"(\d+(?:[.,]\d+)?)", aria)
                            if m:
                                rating_val = float(m.group(1).replace(",", "."))

                        reviews.append({
                            "time"  : time_text,
                            "rating": rating_val,
                            "text"  : review_text,
                        })
                    except:
                        continue

                if not reviews:
                    reviews = None
                else:
                    print(f"[W{worker_id}]   📝 {len(reviews)} review hợp lệ")
                    cap_nhat = parse_cap_nhat_from_review(reviews[0]["time"])

            except Exception as e:
                print(f"[W{worker_id}]   ⚠️ Lỗi tab review: {e}")
            finally:
                await tab2.close()
        else:
            print(f"[W{worker_id}]   ⚠️ Không tìm thấy link Bài đánh giá")

        record.update({
            "tenquan_check"     : tenquan_check,
            "diachi_check"      : diachi_check,
            "diachi_match"      : diachi_match,
            "rate"              : rate,
            "price_level"       : price_level,
            "has_delivery"      : has_delivery,
            "so_dien_thoai"     : so_dien_thoai,
            "gio_mo_cua"        : gio_mo_cua,
            "review"            : reviews,
            "cap_nhat_ngay_dang": cap_nhat,
        })

    except Exception as e:
        print(f"[W{worker_id}]   ✗ Lỗi {video_id}: {e}")
        record.update({**NULL_CHECK, "cap_nhat_ngay_dang": ngay_dang})

    finally:
        await page.close()
        await asyncio.sleep(DELAY_BETWEEN)

    return record


# ─── WORKER ───────────────────────────────────────────

async def worker(worker_id: int, context, queue: asyncio.Queue, results: list):
    while True:
        try:
            idx, record = queue.get_nowait()
        except asyncio.QueueEmpty:
            print(f"[W{worker_id}] 🏁 Queue rỗng → dừng")
            break

        print(f"[W{worker_id}] 🚀 [{idx+1}] {record.get('video_id','?')}")
        updated = await check_record(context, record, worker_id)

        async with file_lock:
            results.append(updated)

        await save_data(results, OUTPUT_FILE)
        print(f"[W{worker_id}] 💾 Lưu [{idx+1}] | Tổng: {len(results)}")
        queue.task_done()


# ─── MAIN ─────────────────────────────────────────────

async def main():
    global warm_pages

    data = load_data(INPUT_FILE)
    if not data:
        print(f"❌ Không đọc được {INPUT_FILE}")
        return

    existing     = load_data(OUTPUT_FILE)
    existing_map = {r["video_id"]: r for r in existing}
    print(f"📂 {INPUT_FILE}: {len(data)} record")
    print(f"📂 {OUTPUT_FILE}: {len(existing_map)} record đã có\n")

    pending = [r for r in data if r["video_id"] not in existing_map]
    print(f"⏳ Cần check: {len(pending)} | Bỏ qua: {len(data) - len(pending)}\n")

    if not pending:
        print("✅ Tất cả đã được check!")
        return

    results     = list(existing)
    pending_len = len(pending)

    queue = asyncio.Queue()
    for i, record in enumerate(pending):
        await queue.put((i, dict(record)))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="vi-VN",
        )

        # ── Warm-up 6 tab ─────────────────────────────
        print("🔥 Warm-up 6 tab browser...")
        warm_pages = []
        for q in WARM_QUERIES:
            wp = await context.new_page()
            await wp.goto(f"https://www.google.com/search?q={q}&hl=vi",
                          wait_until="domcontentloaded", timeout=30000)
            warm_pages.append(wp)
            await asyncio.sleep(1)

        print("\n" + "="*50)
        input("⏳ Xử lý captcha nếu có, xong nhấn Enter...")
        print("="*50 + "\n")
        print("✅ Warm-up xong, bắt đầu check...\n")

        await asyncio.gather(*[
            worker(i, context, queue, results)
            for i in range(min(NUM_WORKERS, pending_len))
        ])

        for wp in warm_pages:
            try:
                await wp.close()
            except:
                pass

        await context.close()
        await browser.close()

    await save_data(results, OUTPUT_FILE)
    print(f"\n✅ XONG! {len(results)} record → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())