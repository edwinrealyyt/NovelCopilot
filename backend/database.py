import os
import json
from typing import List, Dict, Optional

# 本地 JSON 数据库路径
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.json")

class BookRepository:
    def __init__(self):
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """确保底层数据库文件存在并包含默认结构"""
        if not os.path.exists(DB_FILE):
            # 写入一个初始化的空书籍列表结构
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _read_all(self) -> List[Dict]:
        """读取所有书籍"""
        self._ensure_db_exists()
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                data = json.loads(content)
                # 兼容格式：如果 data 是 BookContext 字典，包装成数组
                if isinstance(data, dict) and "BookContext" in data:
                    return [data["BookContext"]]
                elif isinstance(data, dict):
                    # 单本结构
                    return [data]
                return data
        except Exception as e:
            print(f"读取数据库出错: {e}")
            return []

    def _write_all(self, books: List[Dict]):
        """写回所有书籍"""
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(books, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"写入数据库出错: {e}")

    def list_books(self) -> List[Dict]:
        """列出所有书籍的元数据"""
        books = self._read_all()
        return [
            {
                "book_id": b["book_id"],
                "title": b["meta"]["title"],
                "tags": b["meta"]["tags"],
                "synopsis": b["meta"]["synopsis"]
            }
            for b in books
        ]

    def get_book(self, book_id: str) -> Optional[Dict]:
        """获取某本书籍的完整 BookContext"""
        books = self._read_all()
        for b in books:
            if b["book_id"] == book_id:
                return b
        return None

    def save_book(self, book_context: Dict) -> bool:
        """保存或更新一本书"""
        books = self._read_all()
        book_id = book_context["book_id"]
        
        # 查找是否存在并替换，否则追加
        found = False
        for i, b in enumerate(books):
            if b["book_id"] == book_id:
                books[i] = book_context
                found = True
                break
        
        if not found:
            books.append(book_context)
            
        self._write_all(books)
        return True

    def delete_book(self, book_id: str) -> bool:
        """删除一本书"""
        books = self._read_all()
        filtered = [b for b in books if b["book_id"] != book_id]
        if len(filtered) < len(books):
            self._write_all(filtered)
            return True
        return False
