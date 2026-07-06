import os
import json
import threading
import copy
import hashlib
import shutil
from typing import List, Dict, Optional

# 定义数据目录结构
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "data")
BOOKS_DIR = os.path.join(DB_DIR, "books")
INDEX_FILE = os.path.join(DB_DIR, "index.json")

class BookRepository:
    def __init__(self):
        self._lock = threading.Lock()
        self._chapter_hash_cache = {}  # 缓存结构: {(book_id, chapter_id): md5_hash}
        self._ensure_db_exists()
        self._migrate_old_db()

    def _ensure_db_exists(self):
        """确保目录和索引文件存在"""
        os.makedirs(BOOKS_DIR, exist_ok=True)
        if not os.path.exists(INDEX_FILE):
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _save_book_split(self, book_context: Dict, update_cache: bool = True):
        """把一本书的内容深度拆分并写入新文件夹结构中 (供持有 Lock 的方法内部调用)"""
        book_id = book_context["book_id"]
        book_dir = os.path.join(BOOKS_DIR, book_id)
        chapters_dir = os.path.join(book_dir, "chapters")
        os.makedirs(chapters_dir, exist_ok=True)
        
        # 1. 写入 meta.json (只包含元数据和设置)
        meta_file = os.path.join(book_dir, "meta.json")
        meta_data = {
            "book_id": book_id,
            "meta": book_context["meta"],
            "settings": book_context["settings"]
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)
            
        # 2. 深度拷贝 outline，提取正文写入独立文件，并清空 outline 中的正文
        outline_to_save = copy.deepcopy(book_context["outline"])
        
        for volume in outline_to_save.get("volumes", []):
            for chapter in volume.get("chapters", []):
                chapter_id = chapter["chapter_id"]
                content = chapter.get("content") or ""
                
                # 写入章节正文文件
                chapter_file = os.path.join(chapters_dir, f"{chapter_id}.txt")
                
                # 计算新正文的 Hash 校验码
                content_bytes = content.encode("utf-8")
                new_hash = hashlib.md5(content_bytes).hexdigest()
                
                # 获取已有 Hash 缓存
                old_hash = self._chapter_hash_cache.get((book_id, chapter_id))
                
                # 只有在 Hash 不一致或者文件不存在时，才触发磁盘写入
                if new_hash != old_hash or not os.path.exists(chapter_file):
                    with open(chapter_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    if update_cache:
                        self._chapter_hash_cache[(book_id, chapter_id)] = new_hash
                
                # 将 outline 中存储的 content 设为空，减小 outline.json 体积
                chapter["content"] = ""
                
        # 3. 写入轻量化的 outline.json (不包含正文)
        outline_file = os.path.join(book_dir, "outline.json")
        with open(outline_file, "w", encoding="utf-8") as f:
            json.dump(outline_to_save, f, ensure_ascii=False, indent=2)

    def _migrate_old_db(self):
        """支持双重自动迁移：
        1. 迁移根目录下的 data.json 
        2. 迁移 data/books/ 下的单文件 book_id.json
        """
        # 1. 迁移根目录下的原始全量 data.json
        old_db_file = os.path.join(BASE_DIR, "data.json")
        if os.path.exists(old_db_file):
            try:
                print("发现旧的根目录数据库 data.json，正在启动自动迁移...")
                with open(old_db_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        return
                    books = json.loads(content)
                    
                    if isinstance(books, dict):
                        if "BookContext" in books:
                            books = [books["BookContext"]]
                        else:
                            books = [books]
                    elif not isinstance(books, list):
                        books = []
                
                index_data = []
                for book in books:
                    book_id = book.get("book_id")
                    if not book_id:
                        continue
                    
                    # 深度拆分写入
                    self._save_book_split(book, update_cache=False)
                    
                    # 提取元数据索引
                    index_data.append({
                        "book_id": book_id,
                        "title": book.get("meta", {}).get("title", "未命名"),
                        "tags": book.get("meta", {}).get("tags", []),
                        "synopsis": book.get("meta", {}).get("synopsis", "")
                    })
                
                with open(INDEX_FILE, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, ensure_ascii=False, indent=2)
                
                # 备份并移除旧的 data.json 避免重复迁移
                backup_file = os.path.join(BASE_DIR, "data.json.bak")
                os.rename(old_db_file, backup_file)
                print(f"根目录数据迁移成功！已备份为: {backup_file}")
            except Exception as e:
                print(f"迁移旧全量数据库出错: {e}")

        # 2. 检查并迁移之前版本中的单文件书籍 (data/books/{book_id}.json)
        if os.path.exists(BOOKS_DIR):
            for file_name in os.listdir(BOOKS_DIR):
                if file_name.endswith(".json") and file_name != "index.json":
                    old_book_file = os.path.join(BOOKS_DIR, file_name)
                    try:
                        print(f"发现旧版单本 JSON 文件 {file_name}，正在启动拆分迁移...")
                        with open(old_book_file, "r", encoding="utf-8") as f:
                            book = json.load(f)
                        
                        if isinstance(book, dict) and "BookContext" in book:
                            book = book["BookContext"]
                        
                        if isinstance(book, dict) and "book_id" in book:
                            # 深度拆分写入
                            self._save_book_split(book, update_cache=False)
                            
                            # 备份原单本 JSON 文件
                            backup_file = old_book_file + ".bak"
                            os.rename(old_book_file, backup_file)
                            print(f"书籍 {file_name} 拆分迁移成功！已备份为: {backup_file}")
                    except Exception as e:
                        print(f"迁移旧单本书籍文件 {file_name} 出错: {e}")

    def _read_index(self) -> List[Dict]:
        """读取元数据索引 (供持有 Lock 的方法内部调用)"""
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"读取索引出错: {e}")
            return []

    def _write_index(self, index_data: List[Dict]):
        """写回元数据索引 (供持有 Lock 的方法内部调用)"""
        try:
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"写入索引出错: {e}")

    def list_books(self) -> List[Dict]:
        """列出所有书籍的元数据 (直接读取索引，速度极快)"""
        with self._lock:
            return self._read_index()

    def get_book(self, book_id: str) -> Optional[Dict]:
        """获取某本书籍的完整 BookContext (从分割的 meta、outline 与各章节正文中进行拼装)"""
        book_dir = os.path.join(BOOKS_DIR, book_id)
        meta_file = os.path.join(book_dir, "meta.json")
        outline_file = os.path.join(book_dir, "outline.json")
        chapters_dir = os.path.join(book_dir, "chapters")
        
        if not os.path.exists(meta_file) or not os.path.exists(outline_file):
            return None
            
        with self._lock:
            try:
                # 1. 读取 meta.json
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                
                # 2. 读取 outline.json
                with open(outline_file, "r", encoding="utf-8") as f:
                    outline_data = json.load(f)
                
                # 3. 逐个章节读取正文，并更新 Hash 缓存
                for volume in outline_data.get("volumes", []):
                    for chapter in volume.get("chapters", []):
                        chapter_id = chapter["chapter_id"]
                        chapter_file = os.path.join(chapters_dir, f"{chapter_id}.txt")
                        
                        content = ""
                        if os.path.exists(chapter_file):
                            try:
                                with open(chapter_file, "r", encoding="utf-8") as f:
                                    content = f.read()
                            except Exception as e:
                                print(f"读取章节 {chapter_id} 正文出错: {e}")
                        
                        chapter["content"] = content
                        
                        # 载入内存 Hash 缓存，以便后续写入时进行对比过滤
                        content_bytes = content.encode("utf-8")
                        self._chapter_hash_cache[(book_id, chapter_id)] = hashlib.md5(content_bytes).hexdigest()
                
                # 4. 组装完整的 BookContext
                book_context = {
                    "book_id": book_id,
                    "meta": meta_data.get("meta"),
                    "settings": meta_data.get("settings"),
                    "outline": outline_data
                }
                return book_context
            except Exception as e:
                print(f"读取并组装书籍 {book_id} 出错: {e}")
                return None

    def save_book(self, book_context: Dict) -> bool:
        """保存或更新一本书 (仅写入发生变动的文件，极大降低 I/O 开销)"""
        book_id = book_context["book_id"]
        with self._lock:
            try:
                self._save_book_split(book_context, update_cache=True)
            except Exception as e:
                print(f"写入拆分书籍 {book_id} 失败: {e}")
                return False

            # 更新元数据索引
            index_data = self._read_index()
            meta_entry = {
                "book_id": book_id,
                "title": book_context["meta"]["title"],
                "tags": book_context["meta"]["tags"],
                "synopsis": book_context["meta"]["synopsis"]
            }
            
            found = False
            for i, item in enumerate(index_data):
                if item["book_id"] == book_id:
                    index_data[i] = meta_entry
                    found = True
                    break
            
            if not found:
                index_data.append(meta_entry)
                
            self._write_index(index_data)
            return True

    def delete_book(self, book_id: str) -> bool:
        """删除一本书的所有文件、缓存及索引项"""
        book_dir = os.path.join(BOOKS_DIR, book_id)
        
        with self._lock:
            # 1. 递归删除书籍目录
            dir_deleted = False
            if os.path.exists(book_dir):
                try:
                    shutil.rmtree(book_dir)
                    dir_deleted = True
                except Exception as e:
                    print(f"删除书籍目录 {book_id} 失败: {e}")
                    return False
            
            # 清理该书籍相关的 Hash 缓存
            keys_to_remove = [k for k in self._chapter_hash_cache.keys() if k[0] == book_id]
            for k in keys_to_remove:
                self._chapter_hash_cache.pop(k, None)
            
            # 2. 更新索引
            index_data = self._read_index()
            filtered = [b for b in index_data if b["book_id"] != book_id]
            if len(filtered) < len(index_data):
                self._write_index(filtered)
                return True
                
            return dir_deleted
