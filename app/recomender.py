import pandas as pd
import numpy as np
from sqlmodel import select
from sqlalchemy import desc
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import logging

# Impor dari aplikasi kita
from app.db import AsyncSessionLocal
from app.models import ChatMessage
from app.waifu import WAIFU

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Muat model embedding sekali saja
try:
    logger.info("Memuat model Sentence Transformer...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("Model berhasil dimuat.")
except Exception as e:
    logger.error(f"Gagal memuat model: {e}")
    model = None

async def calculate_content_scores(user_id: int, character_vectors: dict) -> dict[str, float]:
    """
    STRATEGI FINAL: Menghitung skor afinitas HANYA berdasarkan 20 pesan TERAKHIR.
    Ini memberikan "Recency Boost", membuat sistem sangat responsif.
    """
    content_scores = {}
    async with AsyncSessionLocal() as session:
        await session.connection(execution_options={"isolation_level": "READ COMMITTED"})
        
        for char_id, char_vector in character_vectors.items():
            # --- PERUBAHAN KUNCI DI SINI ---
            # 1. Ambil HANYA 20 pesan TERBARU user dengan karakter ini.
            stmt = select(ChatMessage).where(
                ChatMessage.user_id == user_id,
                ChatMessage.character_id == char_id
            ).order_by(desc(ChatMessage.timestamp)).limit(20) # Urutkan dari terbaru, ambil 20
            
            result = await session.exec(stmt)
            messages = result.all()
            
            if not messages:
                content_scores[char_id] = 0.0
                continue
            
            # 2. Gabungkan percakapan TERBARU yang relevan.
            conversation_text = " ".join([msg.content for msg in messages])
            
            # 3. Buat vektor dari percakapan spesifik ini.
            conversation_vector = model.encode(conversation_text)
            
            # 4. Hitung kemiripan antara persona karakter dan interaksi TERBARU user.
            similarity = cosine_similarity(
                conversation_vector.reshape(1, -1),
                char_vector.reshape(1, -1)
            )
            content_scores[char_id] = float(similarity[0][0])
            
    logger.info(f"--- SKOR KONTEN (Recency Boost) --- \n{content_scores}\n")
    return content_scores

async def get_all_user_vectors_for_collab() -> dict[int, np.ndarray]:
    """Fungsi bantuan untuk collaborative filtering (tidak berubah)."""
    user_conversations = {}
    async with AsyncSessionLocal() as session:
        await session.connection(execution_options={"isolation_level": "READ COMMITTED"})
        stmt = select(ChatMessage)
        messages = (await session.exec(stmt)).all()
        for msg in messages:
            user_conversations.setdefault(msg.user_id, "")
            user_conversations[msg.user_id] += f"{msg.content} "
    
    return {uid: model.encode(text) for uid, text in user_conversations.items()}

def collaborative_scores(target_user_id: int, user_vectors: dict, all_interactions_df: pd.DataFrame) -> dict:
    """Fungsi ini tidak berubah."""
    if target_user_id not in user_vectors or len(user_vectors) < 2:
        return {}
    target_vector = user_vectors[target_user_id]
    similarities = {
        uid: cosine_similarity(target_vector.reshape(1, -1), vec.reshape(1, -1))[0][0]
        for uid, vec in user_vectors.items() if uid != target_user_id
    }
    if not similarities:
        return {}
    similar_users = sorted(similarities.items(), key=lambda item: item[1], reverse=True)[:5]
    recommended_chars = {}
    for user_id, score in similar_users:
        liked_chars = all_interactions_df[all_interactions_df['user_id'] == user_id]['character_id'].tolist()
        for char in liked_chars:
            recommended_chars.setdefault(char, 0.0)
            recommended_chars[char] += float(score)
    return recommended_chars

async def hybrid_recommendation(user_id: int, alpha: float = 0.7) -> list[str]:
    if model is None:
        return []

    logger.info(f"--- MEMULAI REKOMENDASI (STRATEGI FINAL DENGAN RECENCY BOOST) UNTUK USER: {user_id} ---")

    character_prompts = {char_id: data['system_prompt'] for char_id, data in WAIFU.items()}
    character_vectors = {char_id: model.encode(prompt) for char_id, prompt in character_prompts.items()}

    content_scores = await calculate_content_scores(user_id, character_vectors)

    user_vectors_for_collab = await get_all_user_vectors_for_collab()
    async with AsyncSessionLocal() as session:
        await session.connection(execution_options={"isolation_level": "READ COMMITTED"})
        stmt = select(ChatMessage.user_id, ChatMessage.character_id).distinct()
        interactions = (await session.exec(stmt)).all()
        all_interactions_df = pd.DataFrame(interactions, columns=['user_id', 'character_id'])
    
    collab_scores = collaborative_scores(user_id, user_vectors_for_collab, all_interactions_df)
    max_collab_score = max(collab_scores.values()) if collab_scores else 1.0
    collab_scores_normalized = {char: score / max_collab_score for char, score in collab_scores.items()}
    logger.info(f"--- SKOR KOLABORATIF (Normalized) --- \n{collab_scores_normalized}\n")

    final_scores = {}
    all_char_ids = set(content_scores.keys()) | set(collab_scores_normalized.keys())
    for char_id in all_char_ids:
        content = content_scores.get(char_id, 0.0)
        collab = collab_scores_normalized.get(char_id, 0.0)
        final_scores[char_id] = (alpha * content) + ((1 - alpha) * collab)
    logger.info(f"--- SKOR FINAL GABUNGAN --- \n{final_scores}\n")

    interacted_chars = set(all_interactions_df[all_interactions_df['user_id'] == user_id]['character_id'].unique())
    scores_to_sort = final_scores

    sorted_recommendations = sorted(scores_to_sort.items(), key=lambda item: item[1], reverse=True)
    recommendation_ids = [char_id for char_id, score in sorted_recommendations[:3]]
    logger.info(f"--- REKOMENDASI FINAL --- \n{recommendation_ids}\n")
    
    return recommendation_ids