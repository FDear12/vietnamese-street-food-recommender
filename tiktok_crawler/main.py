# main.py
import asyncio
import sys
from step1_crawl   import main as crawl
from step2_extract import main as extract
from step3_pack    import main as pack   # ← đổi tên từ step4_pack.py → step3_pack.py

def print_banner():
    print("""
╔══════════════════════════════════════════╗
║       TikTok Food Crawler Pipeline       ║
║  Step1 Crawl → Step2 Extract+OCR →      ║
║  Step3 Pack ZIP                          ║
║  (Colab: Step4 Qianfan → 5 → 6 → 7)    ║
╚══════════════════════════════════════════╝
    """)

def print_step(step: int, name: str):
    print(f"\n{'='*50}")
    print(f"  STEP {step}: {name}")
    print(f"{'='*50}\n")

def main():
    print_banner()

    print_step(1, "Playwright - Crawl TikTok")
    asyncio.run(crawl())

    print_step(2, "ffmpeg Extract + PaddleOCR Filter")
    extract()

    print_step(3, "Pack ZIP")
    pack()

    print("""
╔══════════════════════════════════════════╗
║           ✅ PIPELINE HOÀN TẤT!          ║
║   images.zip sẵn sàng → upload Drive    ║
║   Mang lên Colab chạy Qianfan OCR!       ║
╚══════════════════════════════════════════╝
    """)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--step":
        step = int(sys.argv[2])
        if step == 1:
            print_step(1, "Playwright - Crawl TikTok")
            asyncio.run(crawl())
        elif step == 2:
            print_step(2, "ffmpeg Extract + PaddleOCR Filter")
            extract()
        elif step == 3:
            print_step(3, "Pack ZIP")
            pack()
        else:
            print(f"⚠️  Step {step} chạy trên Colab, không chạy local!")
    else:
        main()