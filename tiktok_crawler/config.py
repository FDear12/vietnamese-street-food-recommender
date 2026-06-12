# config.py

# ─── HASHTAG CHÍNH (food/loai_hinh) ───────────────────
HASHTAG_CHINH = {
    "banhbeo"       : "Bánh Bèo",#
    "banhbotloc"    : "Bánh Bột Lọc",#
    "banhcan"       : "Bánh Căn",#
    "banhcanh"      : "Bánh Canh",#
    "banhbao"       : "Bánh Bao",#
    "banhcuon"      : "Bánh Cuốn",#
    "banhkhot"      : "Bánh Khọt",#
    
    "banhtrangnuong": "Bánh Tráng Nướng",#
    "banhxeo"       : "Bánh Xèo",#
    "bunbohue"      : "Bún Bò Huế",#
    "buncha"        : "Bún Chả",#
    "bundaumamtom"  : "Bún Đậu Mắm Tôm",#
    "bunmam"        : "Bún Mắm",#
    "bunrieu"       : "Bún Riêu",#
    "bunthitnuong"  : "Bún Thịt Nướng",#
    "caolau"        : "Cao Lầu",#
    "chaolong"      : "Cháo Lòng", #
    "comtam"        : "Cơm Tấm",
    
    "hutieu"        : "Hủ Tiếu", #
    
    "nemchua"       : "Nem Chua",#
    "pho"           : "Phở",#
    
    "miquang"       : "Mì Quảng",#
}

# ─── HASHTAG PHỤ TRỢ (location/context) ───────────────
HASHTAG_PHU_TRO = [
    "quanan", "diachi", "danang", "hcm", "hanoi",
    "saigon", "review", "amthuc", "monngon",
]

# ─── SEARCH LOCATIONS ─────────────────────────────────
SEARCH_LOCATIONS = {
    "Đà Nẵng"     : ["danang"],
    "Hồ Chí Minh" : ["saigon", "hochiminh", "hcm"],
    "Hà Nội"      : ["hanoi"],
    "Toàn quốc"   : [],   # chỉ #hashtag quanan, không kèm thành phố
}

# ─── SEARCH SUFFIX ────────────────────────────────────
SEARCH_SUFFIX = "quanan"

# ─── FILTER ───────────────────────────────────────────
MAX_DAYS_OLD = 30

# ─── FRAME EXTRACTION ─────────────────────────────────
BLUR_THRESHOLD  = 100
PHASH_THRESHOLD = 10
FPS_EXTRACT     = 1

# ─── PADDLEOCR ────────────────────────────────────────
ADDRESS_KEYWORDS = [
    "đường", "phường", "quận", "huyện",
    "tỉnh", "tp.", "số ", "p.", "q.",
    "thành phố", "district", "street"
]

# ─── OUTPUT ───────────────────────────────────────────
IMAGE_DIR  = "images"
META_FILE  = "metadata.json"
OUTPUT_ZIP = "images.zip"