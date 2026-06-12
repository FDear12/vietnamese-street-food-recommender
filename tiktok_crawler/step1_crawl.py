# step1_crawl.py
import json
import asyncio
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from config import HASHTAG_CHINH, HASHTAG_PHU_TRO, MAX_DAYS_OLD, META_FILE, SEARCH_SUFFIX, SEARCH_LOCATIONS

# ─── LOCK ─────────────────────────────────────────────
meta_lock   = asyncio.Lock()
scroll_lock = asyncio.Lock()

SCROLL_STATE_FILE = "scroll_state.json"
MAX_COLLECT       = 100   # mỗi (hashtag × location)
MAX_NO_NEW        = 3     # scroll liên tiếp không có card mới → thoát
NUM_WORKERS       = 3     # số tab chạy song song
RESET_EVERY       = 30     # reset context sau mỗi N search mới hoàn thành

# ─── HELPER ───────────────────────────────────────────

def get_hashtag_chinh(hashtags_raw: list[str]) -> str | None:
    for tag in hashtags_raw:
        tag_clean = re.sub(r'[^a-z]', '', tag.lower())
        for key in HASHTAG_CHINH:
            if key == "banhcan":
                if tag_clean == key:
                    return key
            else:
                if key in tag_clean:
                    return key
    return None

def parse_date(text: str) -> str | None:
    try:
        now = datetime.now()
        t = re.sub(r"[·•]", "", text).strip().lower()

        m = re.search(r"(\d+)\s*(h|hour|giờ)", t)
        if m:
            return now.strftime("%Y-%m-%d")

        m = re.search(r"(\d+)\s*(d|day|ngày)", t)
        if m:
            return (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")

        m = re.search(r"(\d+)\s*(w|week|tuần)", t)
        if m:
            return (now - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m-%d")

        m = re.search(r"(\d+)\s*(mo|month|tháng)", t)
        if m:
            return (now - timedelta(days=int(m.group(1)) * 30)).strftime("%Y-%m-%d")

        t_orig = re.sub(r"[·•]", "", text).strip()
        parts = t_orig.split("-")
        if len(parts) == 3:
            y, mo, d = parts
            return f"{y.strip()}-{int(mo.strip()):02d}-{int(d.strip()):02d}"
        if len(parts) == 2:
            mo, d = parts
            return f"{now.year}-{int(mo.strip()):02d}-{int(d.strip()):02d}"
    except:
        pass
    return None

def is_within_days(date_str: str, max_days: int) -> bool:
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        return datetime.now() - date <= timedelta(days=max_days)
    except:
        return False

def load_existing_meta() -> dict:
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {r["video_id"]: r for r in data}
    except:
        return {}

async def save_meta_safe(records: dict):
    async with meta_lock:
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(list(records.values()), f, ensure_ascii=False, indent=2)
        print(f"💾 Đã lưu {len(records)} video vào {META_FILE}")

def load_scroll_state() -> dict:
    try:
        with open(SCROLL_STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

async def save_scroll_state(state: dict):
    async with scroll_lock:
        with open(SCROLL_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

def build_search_query(hashtag: str, location_key: str) -> str:
    keywords = SEARCH_LOCATIONS[location_key]
    if keywords:
        kw_str = " ".join(keywords)
        return f"%23{hashtag}%20{SEARCH_SUFFIX}%20{kw_str}"
    else:
        return f"%23{hashtag}%20{SEARCH_SUFFIX}"

def state_key(hashtag: str, location_key: str) -> str:
    return f"{hashtag}__{location_key}"

def count_collected(records: dict, hashtag: str, location_key: str) -> int:
    """Đếm số video đã có cho cặp (hashtag × location) từ config."""
    return sum(
        1 for r in records.values()
        if r["hashtag_chinh"] == hashtag and r.get("location_search") == location_key
    )

def find_resume_start(all_tasks: list, scroll_state: dict) -> int:
    """Tìm index bắt đầu = task thứ 3 từ bottom trong scroll_state.
    Bottom = key cuối cùng trong scroll_state khớp với all_tasks."""
    valid_keys = [state_key(h, l) for h, l in all_tasks]
    matched = [k for k in scroll_state.keys() if k in valid_keys]
    if not matched:
        return 0
    # Lấy thứ 3 từ bottom (index -5), nếu không đủ thì lấy đầu tiên
    target = matched[-4] if len(matched) >= 4 else matched[0]
    for i, (h, l) in enumerate(all_tasks):
        if state_key(h, l) == target:
            return i
    return 0


# ─── LẤY META TỪ VIDEO PAGE ───────────────────────────

async def get_video_meta(context, video_url: str) -> dict:
    tab = await context.new_page()
    try:
        await tab.goto(video_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # ── Hashtags ─────────────────────────────────
        hashtags_raw = []
        tag_els = await tab.query_selector_all('a[href*="/tag/"]')
        for el in tag_els:
            try:
                t = (await el.inner_text()).strip().lower().replace("#", "")
                if t:
                    hashtags_raw.append(f"#{t}")
            except:
                pass

        if not hashtags_raw:
            for sel in [
                '[data-e2e="browse-video-desc"]',
                '[data-e2e="video-desc"]',
                'h1[data-e2e="video-desc"]',
            ]:
                el = await tab.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    tags = re.findall(r"#(\w+)", text.lower())
                    hashtags_raw = [f"#{t}" for t in tags]
                    break

        # ── Ngày đăng ────────────────────────────────
        ngay_dang = None
        date_raw  = None

        date_els = await tab.query_selector_all('div[class*="DivCreatorInfoContainer"] span')
        for el in date_els:
            try:
                t = (await el.inner_text()).strip()
                if "·" in t or re.search(r"\d", t):
                    date_raw  = t
                    ngay_dang = parse_date(t)
                    if ngay_dang:
                        break
            except:
                pass

        print(f"    📌 Hashtags : {hashtags_raw}")
        print(f"    📅 Raw date : {date_raw!r} → {ngay_dang}")

        return {
            "hashtags_raw": hashtags_raw,
            "ngay_dang"   : ngay_dang or "unknown",
        }

    finally:
        await tab.close()


# ─── CRAWL 1 (HASHTAG × LOCATION) ────────────────────

async def crawl_one(page, context, hashtag: str, location_key: str,
                    records: dict, scroll_state: dict, worker_id: int):

    skey = state_key(hashtag, location_key)
    collected = count_collected(records, hashtag, location_key)
    print(f"\n[W{worker_id}] 🔍 [{hashtag} × {location_key}] Resume: đã có {collected}/{MAX_COLLECT}")

    if collected >= MAX_COLLECT:
        print(f"[W{worker_id}]   ✅ Đã đủ {MAX_COLLECT}, bỏ qua")
        return

    query      = build_search_query(hashtag, location_key)
    search_url = f"https://www.tiktok.com/search?q={query}&t=1"
    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    # Click tab Videos
    #try:
       # videos_tab = await page.query_selector('button[data-testid="tux-web-tab-bar"]:has-text("Videos")')
       # if videos_tab:
         #   await videos_tab.click()
       #     await asyncio.sleep(2)
       #     print(f"[W{worker_id}]   → Đã click tab Videos")
    #except Exception as e:
       # print(f"[W{worker_id}]   ⚠️ Lỗi click tab Videos: {e}")

    scroll_count  = 0
    processed_ids = set()
    tab_opened    = 0
    no_new        = 0

    # ── Fast-scroll resume ────────────────────────────
    resume_scroll = scroll_state.get(skey, 0)
    if resume_scroll > 0:
        print(f"[W{worker_id}]   ⏩ Fast-scroll resume tới {resume_scroll}...")
        for _ in range(resume_scroll):
            await page.evaluate("window.scrollBy(0, 900)")
            await asyncio.sleep(1)
        scroll_count = resume_scroll
        print(f"[W{worker_id}]   ✅ Đã fast-scroll tới {resume_scroll}")

    while True:
        # ── Re-check đủ mẫu (records có thể được update bởi worker khác) ──
        collected = count_collected(records, hashtag, location_key)
        if collected >= MAX_COLLECT:
            print(f"[W{worker_id}]   ✅ Đủ {MAX_COLLECT} bài → chuyển search tiếp")
            break

        cards = await page.query_selector_all('[data-e2e="search_video-item"]')
        if not cards:
            cards = await page.query_selector_all('[data-e2e="search_top-item"]')
        print(f"[W{worker_id}]   [{hashtag}×{location_key}] {len(cards)} cards | {collected}/{MAX_COLLECT}")

        new_this_round = 0

        for card in cards:
            # Re-check bên trong vòng for cũng để thoát sớm
            collected = count_collected(records, hashtag, location_key)
            if collected >= MAX_COLLECT:
                break
            try:
                a_tag = await card.query_selector("a[href*='/video/']")
                if not a_tag:
                    continue
                href = await a_tag.get_attribute("href")
                if not href or "/video/" not in href:
                    continue

                video_id = "tk_" + href.split("/video/")[1].split("?")[0]
                if video_id in records or video_id in processed_ids:
                    continue

                processed_ids.add(video_id)
                new_this_round += 1

                if href.startswith("/"):
                    href = "https://www.tiktok.com" + href

                print(f"\n[W{worker_id}]   [{collected+1}/{MAX_COLLECT}] {video_id}")

                meta = await get_video_meta(context, href)
                tab_opened += 1

                # Scroll phụ sau mỗi 6 tab mở
                if tab_opened % 6 == 0:
                    await card.scroll_into_view_if_needed()
                    await page.evaluate("window.scrollBy(0, 900)")
                    await asyncio.sleep(2)

                # Filter hashtag food
                hashtag_chinh = get_hashtag_chinh(meta["hashtags_raw"])
                if not hashtag_chinh:
                    print(f"[W{worker_id}]   ✗ Không có hashtag food")
                    continue
                if hashtag_chinh != hashtag:
                    print(f"[W{worker_id}]   ✗ Sai hashtag: {hashtag_chinh} != {hashtag}")
                    continue

                # Filter thời gian
                ngay_dang = meta["ngay_dang"]
                duyet = ngay_dang != "unknown" and is_within_days(ngay_dang, MAX_DAYS_OLD)

                hashtags_useful = [
                    t for t in meta["hashtags_raw"]
                    if any(k in t for k in list(HASHTAG_CHINH.keys()) + HASHTAG_PHU_TRO)
                ]

                record = {
                    "video_id"       : video_id,
                    "url"            : href,
                    "hashtag_chinh"  : hashtag_chinh,
                    "location_search": location_key,
                    "ngay_dang"      : ngay_dang,
                    "duyet"          : duyet,
                    "hashtags_useful": hashtags_useful,
                    "hashtags_raw"   : meta["hashtags_raw"],
                    "frame"          : None,
                }

                async with meta_lock:
                    records[video_id] = record
                await save_meta_safe(records)
                collected += 1
                print(f"[W{worker_id}]   ✓ Saved: {video_id} | {ngay_dang} | duyet={duyet} | loc={location_key}")

            except Exception as e:
                print(f"[W{worker_id}]   ✗ Lỗi: {e}")
                continue

        # ── Scroll chính ──────────────────────────────
        if new_this_round == 0:
            no_new += 1
            print(f"[W{worker_id}]   → Scroll {scroll_count} | Không card mới ({no_new}/{MAX_NO_NEW})")
            if no_new >= MAX_NO_NEW:
                print(f"[W{worker_id}]   🛑 {MAX_NO_NEW} scroll không có card mới → chuyển search tiếp")
                break
        else:
            no_new = 0

        await page.evaluate("window.scrollBy(0, 900)")
        await asyncio.sleep(2)
        scroll_count += 1
        scroll_state[skey] = scroll_count
        await save_scroll_state(scroll_state)
        print(f"[W{worker_id}]   → Scroll {scroll_count}")

    print(f"[W{worker_id}]   🏁 [{hashtag} × {location_key}] Kết thúc: {count_collected(records, hashtag, location_key)}/{MAX_COLLECT}")


# ─── WORKER ───────────────────────────────────────────

async def worker(worker_id: int, context, queue: asyncio.Queue,
                 records: dict, scroll_state: dict):
    page = await context.new_page()
    try:
        while True:
            try:
                hashtag, location_key = queue.get_nowait()
            except asyncio.QueueEmpty:
                print(f"[W{worker_id}] 🏁 Queue rỗng → worker dừng")
                break

            # Re-check: worker khác có thể đã fill xong cặp này
            collected = count_collected(records, hashtag, location_key)
            if collected >= MAX_COLLECT:
                print(f"[W{worker_id}] ⏭️  Skip {hashtag}×{location_key} — đã đủ ({collected}/{MAX_COLLECT})")
                queue.task_done()
                continue

            print(f"[W{worker_id}] 🚀 Nhận task: {hashtag} × {location_key}")
            await crawl_one(page, context, hashtag, location_key,
                            records, scroll_state, worker_id)
            queue.task_done()
            print(f"[W{worker_id}] ✅ Xong {hashtag}×{location_key} → lấy task mới ngay")

    finally:
        await page.close()
        print(f"[W{worker_id}] 🔒 Page đã đóng")


# ─── MAIN ─────────────────────────────────────────────

async def make_context(browser, cookies: list):
    """Tạo context mới và load cookies."""
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    if cookies:
        await context.add_cookies(cookies)
    return context


# ─── MAIN ─────────────────────────────────────────────

async def main():
    records      = load_existing_meta()
    scroll_state = load_scroll_state()
    print(f"📂 Resume: đã có {len(records)} video\n")

    # Build danh sách từ config (hashtag × location)
    all_tasks = [
        (hashtag, loc)
        for hashtag in HASHTAG_CHINH.keys()
        for loc in SEARCH_LOCATIONS.keys()
    ]

    # Tìm index bắt đầu (thứ 3 từ bottom trong scroll_state)
    start_idx = find_resume_start(all_tasks, scroll_state)
    print(f"▶️  Resume từ task index {start_idx}: {all_tasks[start_idx]}\n")

    # Thống kê + build task list từ start_idx, bỏ qua task đã đủ
    pending_tasks = []
    print("📊 Thống kê hiện tại:")
    for i, (hashtag, loc) in enumerate(all_tasks):
        collected = count_collected(records, hashtag, loc)
        if i < start_idx:
            print(f"  ⏭️  #{hashtag} × {loc}: {collected}/{MAX_COLLECT} — trước resume, skip")
        elif collected >= MAX_COLLECT:
            print(f"  ✅ #{hashtag} × {loc}: {collected}/{MAX_COLLECT} — đủ, skip")
        else:
            print(f"  ⏳ #{hashtag} × {loc}: {collected}/{MAX_COLLECT} — cần thêm {MAX_COLLECT - collected}")
            pending_tasks.append((hashtag, loc))

    print(f"\n→ {len(pending_tasks)} task cần crawl ({NUM_WORKERS} workers song song)\n")

    if not pending_tasks:
        print("✅ Tất cả đã đủ dữ liệu!")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        # Load cookies lần đầu
        saved_cookies = []
        try:
            with open("cookies.json", "r") as f:
                saved_cookies = json.load(f)
            print("🍪 Loaded cookies!")
        except:
            print("⚠️ Chưa có cookies, cần login thủ công!")

        context = await make_context(browser, saved_cookies)

        # Login
        page0 = await context.new_page()
        await page0.goto("https://www.tiktok.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        print("\n" + "="*50)
        input("⏳ Login TikTok xong thì nhấn Enter...")
        print("="*50 + "\n")

        saved_cookies = await context.cookies()
        with open("cookies.json", "w") as f:
            json.dump(saved_cookies, f)
        print("🍪 Saved cookies!\n")
        await page0.close()

        # Chia pending_tasks thành batch RESET_EVERY task
        # Mỗi batch chạy NUM_WORKERS workers song song, xong thì reset context
        searches_done = 0
        for batch_start in range(0, len(pending_tasks), RESET_EVERY):
            batch = pending_tasks[batch_start: batch_start + RESET_EVERY]

            print(f"\n{'='*50}")
            print(f"🔄 Batch {batch_start//RESET_EVERY + 1} | Task {batch_start+1}–{batch_start+len(batch)}/{len(pending_tasks)}")
            print(f"   {batch}")
            print(f"{'='*50}")

            # Build queue cho batch này
            queue = asyncio.Queue()
            for task in batch:
                await queue.put(task)

            # Chạy workers
            await asyncio.gather(*[
                worker(i, context, queue, records, scroll_state)
                for i in range(min(NUM_WORKERS, len(batch)))
            ])

            searches_done += len(batch)
            print(f"\n✅ Batch xong | Tổng search: {searches_done} | Video: {len(records)}")

            # Reset context sau mỗi batch (trừ batch cuối)
            if batch_start + RESET_EVERY < len(pending_tasks):
                print(f"♻️  Reset context để giải phóng RAM...")
                await context.close()
                context = await make_context(browser, saved_cookies)
                print(f"♻️  Context mới sẵn sàng\n")

        await context.close()
        await browser.close()

    print(f"\n✅ XONG! Tổng: {len(records)} video")
    print("\n📊 Kết quả cuối:")
    for hashtag, loc in all_tasks:
        collected = count_collected(records, hashtag, loc)
        status = "✅" if collected >= MAX_COLLECT else f"⚠️  thiếu {MAX_COLLECT - collected}"
        print(f"  #{hashtag} × {loc}: {collected}/{MAX_COLLECT} {status}")


if __name__ == "__main__":
    asyncio.run(main())