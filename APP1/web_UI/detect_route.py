"""
detect_route.py
───────────────
Blueprint Flask cho tính năng "Kiểm tra món ăn".
Cách dùng: import và register vào app.py chính.

    from detect_route import detect_bp
    app.register_blueprint(detect_bp)
"""

import io
import os
import json
import torch
import torch.nn as nn
from PIL import Image
from flask import Blueprint, request, jsonify, render_template
import torchvision.transforms as T

# ── CONFIG ──────────────────────────────────────────────────────
CHECKPOINT_PATH = "model/best_model.pth"
IMG_SIZE    = 288                          # phải khớp với lúc train
TOP_K       = 5                            # trả top-K predictions
DEVICE      = "cuda" if torch.cuda.is_available() else "cpu"
# Thêm dict này vào đầu file detect_route.py
HASHTAG_DISPLAY = {
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
    "miquang"       : "Mì Quảng",
}
# ── BLUEPRINT ────────────────────────────────────────────────────
detect_bp = Blueprint("detect", __name__)

# ── MODEL — load 1 lần khi import ───────────────────────────────
_model      = None
_class_names = None

def _load_model():
    global _model, _class_names
    if _model is not None:
        return _model, _class_names

    if not os.path.isfile(CHECKPOINT_PATH):
        raise FileNotFoundError(
            f"Không tìm thấy checkpoint: {CHECKPOINT_PATH}\n"
            f"Đặt file best_model.pth vào thư mục checkpoints/ "
            f"hoặc set env FOOD_MODEL_PATH."
        )

    try:
        import timm
    except ImportError:
        raise ImportError("Cần cài timm: pip install timm")

    ckpt = torch.load(CHECKPOINT_PATH, map_location=DEVICE)

    # Lấy class_names từ checkpoint (được lưu lúc train)
    _class_names = ckpt.get("class_names", [])
    num_classes  = len(_class_names)

    if num_classes == 0:
        raise ValueError(
            "Checkpoint không chứa 'class_names'. "
            "Hãy kiểm tra lại file best_model.pth."
        )

    # Rebuild model
    _model = timm.create_model(
        "tf_efficientnetv2_s",
        pretrained=False,
        num_classes=num_classes,
    )
    _model.load_state_dict(ckpt["model_state_dict"])
    _model.to(DEVICE)
    _model.eval()

    print(f"[detect] ✅ Model loaded — {num_classes} classes — device={DEVICE}")
    return _model, _class_names


# ── TRANSFORM (giống eval_transform lúc train) ──────────────────
_transform = T.Compose([
    T.Resize((IMG_SIZE, IMG_SIZE)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406],
                std =[0.229, 0.224, 0.225]),
])


def predict(image_bytes: bytes) -> list[dict]:
    """
    Nhận bytes ảnh, trả danh sách top-K dict:
        [{"label": "bun bo", "confidence": 0.923}, ...]
    """
    model, class_names = _load_model()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = _transform(img).unsqueeze(0).to(DEVICE)   # [1, C, H, W]

    with torch.no_grad():
        logits = model(tensor)                          # [1, num_classes]
        probs  = torch.softmax(logits, dim=1)[0]       # [num_classes]

    # Lấy top-K
    topk_probs, topk_idx = torch.topk(probs, k=min(TOP_K, len(class_names)))

    results = [
        {
            "label"     : HASHTAG_DISPLAY.get(class_names[idx.item()], class_names[idx.item()]),
            "confidence": round(prob.item(), 4),
        }
        for prob, idx in zip(topk_probs, topk_idx)
    ]
    return results


# ── ROUTES ──────────────────────────────────────────────────────
@detect_bp.route("/detect-food")
def detect_page():
    """Render trang Kiểm tra món ăn."""
    return render_template("detect.html")


@detect_bp.route("/detect", methods=["POST"])
def detect_api():
    """
    POST /detect
    Body   : multipart/form-data, field 'image'
    Returns: JSON {"predictions": [...]} hoặc {"error": "..."}
    """
    if "image" not in request.files:
        return jsonify({"error": "Thiếu field 'image' trong request"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Chưa chọn file"}), 400

    # Kiểm tra MIME type cơ bản
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        return jsonify({"error": f"Định dạng không hỗ trợ: {file.content_type}"}), 415

    image_bytes = file.read()
    if len(image_bytes) > 10 * 1024 * 1024:   # giới hạn 10MB
        return jsonify({"error": "File quá lớn (max 10 MB)"}), 413

    try:
        preds = predict(image_bytes)
        return jsonify({"predictions": preds})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        print(f"[detect] ❌ Error: {e}")
        return jsonify({"error": f"Lỗi nhận diện: {str(e)}"}), 500