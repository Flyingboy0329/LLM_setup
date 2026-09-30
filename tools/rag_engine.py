import os
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "Knowledge"
DB_DIR = PROJECT_ROOT / "data" / "chroma"

class LocalRAG:
    def __init__(self):
        self.collection = None
        self._init_db()

    def _init_db(self):
        """初始化輕量本機向量庫 (零顯存開銷)"""
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            # 使用本地 CPU 輕量嵌入函式，不佔用 Nvidia VRAM
            emb_fn = embedding_functions.DefaultEmbeddingFunction()
            client = chromadb.PersistentClient(path=str(DB_DIR))
            self.collection = client.get_or_create_collection(
                name="local_knowledge",
                embedding_function=emb_fn
            )
        except Exception as e:
            print(f"[WARN] RAG 向量庫初始化略過 (缺少 chromadb): {e}")

    def ingest_documents(self) -> str:
        """掃描 Knowledge/ 資料夾內的文件並建立索引"""
        if not self.collection:
            return "❌ RAG 向量引擎未就緒。"

        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        supported_exts = {".txt", ".md"}
        total_chunks = 0

        for file_path in KNOWLEDGE_DIR.iterdir():
            if file_path.suffix.lower() in supported_exts:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()

                    # 簡單滑動視窗切片 (每 500 字一片，重疊 50 字)
                    chunks = [text[i:i+500] for i in range(0, len(text), 450)]
                    for idx, chunk in enumerate(chunks):
                        doc_id = f"{file_path.name}_chunk_{idx}"
                        self.collection.upsert(
                            ids=[doc_id],
                            documents=[chunk],
                            metadatas=[{"source": file_path.name}]
                        )
                        total_chunks += 1
                except Exception as e:
                    print(f"[ERR] 讀取 {file_path.name} 失敗: {e}")

        return f"✅ 知識庫同步完成！已成功索引 {total_chunks} 個文檔切片。"

    def query(self, user_query: str, top_k: int = 2) -> str:
        """依使用者問題檢索關聯度最高的知識庫內容"""
        if not self.collection or self.collection.count() == 0:
            return ""

        try:
            results = self.collection.query(
                query_texts=[user_query],
                n_results=top_k
            )
            retrieved_docs = results.get("documents", [[]])[0]
            if not retrieved_docs:
                return ""

            formatted_results = []
            for doc in retrieved_docs:
                formatted_results.append(f"- 參考資料片段：{doc.strip()}")
            return "\n".join(formatted_results)
        except Exception as e:
            print(f"[WARN] RAG 查詢失敗: {e}")
            return ""

# 單例模式方便跨模組調用
rag_engine = LocalRAG()