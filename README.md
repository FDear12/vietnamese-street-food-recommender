# 🍜 Vietnamese Street Food Recommender

> *Discover trending street food restaurants in Vietnam — powered by real TikTok social data.*

Vietnam is one of the world's greatest destinations for food lovers. From smoky bánh mì carts to steaming bowls of phở, the country's street food culture is vibrant, deeply local, and endlessly diverse. If you're looking to explore authentic culinary experiences — Vietnam is the perfect choice.

This system taps directly into **TikTok social trends** to recommend the most talked-about, visited, and loved street food restaurants across Vietnamese cities. Every recommendation is backed by real video data, regularly updated to reflect what's actually trending right now.

## ✨ Why this project?

- 🔥 **Trend-driven** — restaurant data sourced from viral TikTok content, reflecting what real people are eating and loving
- 🕐 **Always fresh** — dataset continuously verified and updated for accuracy
- 🤝 **Attentive service** — RAG-powered chatbot understands your preferences and guides you to the right spot
- 🌏 **Diverse & inclusive** — covers 22+ food categories across multiple Vietnamese cities, from Đà Nẵng to Hà Nội and beyond

<img width="940" height="477" alt="image" src="https://github.com/user-attachments/assets/d4897856-091f-4c17-bb1c-8f6d7581b280" />

## 🔧 System Pipeline

<img width="673" height="821" alt="pipeline" src="https://github.com/user-attachments/assets/1b198a65-5388-4ebf-a274-9d567abd6c48" />

## 📁 Project Structure

```
APP/
├── tiktok_crawler/        # 1-3: crawl, download, OCR
│   └── metadata.json
├── data_v2/
│   └── data.json
└── web_UI/                 # Flask web app
    ├── app.py
    ├── templates/
    └── static/
```

## 📦 Dataset

Video frame data used for restaurant extraction is publicly available on Kaggle:

👉 [TikTok Video Frame Filter Dataset](https://www.kaggle.com/datasets/nnhnhh/data-video-frame-filter)

## 📬 Contact

Email: dnhn2k4@gmail.com
