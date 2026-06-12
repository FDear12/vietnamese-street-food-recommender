# main.py
from RAGChatBot import review_chain

history = []  # lưu lịch sử hội thoại

def generate_response(question):
    # Thêm câu hỏi mới vào history
    history.append(f"User: {question}")
    
    # Lấy 6 tin nhắn gần nhất làm context
    conversation = "\n".join(history[-6:])
    
    # Gọi RAG với toàn bộ đoạn hội thoại
    result = review_chain(conversation)
    
    # Lưu câu trả lời vào history
    history.append(f"Bot: {result}")
    
    return result