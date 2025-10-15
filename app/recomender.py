import pandas as pd
import random
from sqlmodel import select
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler

# Impor dari aplikasi kita
from app.db import get_async_session
from app.models import Interaction
from app.waifu import WAIFU

async def get_interaction_data() -> pd.DataFrame:
    """
    Mengambil semua data interaksi dari database dan mengubahnya menjadi DataFrame.
    """
    async for session in get_async_session():
        stmt = select(Interaction)
        result = await session.exec(stmt)
        interactions = result.all()

        if not interactions:
            return pd.DataFrame(columns=["user_id", "character_id", "message_count"])

        df = pd.DataFrame(
            [
                {
                    "user_id": i.user_id,
                    "character_id": i.character_id,
                    "message_count": i.message_count,
                }
                for i in interactions
            ]
        )
        return df

def content_based_filtering(user_history: pd.DataFrame, all_waifus: dict) -> dict:
    """
    Memberikan skor berdasarkan kemiripan deskripsi karakter (Content-Based).
    """
    if user_history.empty:
        return {}
    # ... (Logika ini sudah benar dan tidak diubah)
    interacted_char_ids = user_history["character_id"].unique()
    user_profile_texts = [all_waifus[cid]['description'] for cid in interacted_char_ids if cid in all_waifus]
    if not user_profile_texts: return {}
    user_profile_doc = " ".join(user_profile_texts)
    waifu_items = list(all_waifus.values())
    waifu_ids = [w['id'] for w in waifu_items]
    waifu_descriptions = [w['description'] for w in waifu_items]
    documents = [user_profile_doc] + waifu_descriptions
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(documents)
    cosine_sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])
    return {waifu_ids[i]: score for i, score in enumerate(cosine_sim[0])}

def collaborative_filtering(user_id: int, all_interactions: pd.DataFrame) -> dict:
    """
    [LOGIKA BARU]
    Memberikan skor berdasarkan kemiripan dengan pengguna lain (Collaborative Filtering).
    """
    if all_interactions.empty or user_id not in all_interactions['user_id'].values:
        return {}

    # 1. Buat matriks user-item: baris=user, kolom=karakter, nilai=jumlah pesan
    user_item_matrix = all_interactions.pivot_table(
        index='user_id', columns='character_id', values='message_count'
    ).fillna(0)
    
    # 2. Hitung kemiripan antar pengguna menggunakan cosine similarity
    user_similarity = cosine_similarity(user_item_matrix)
    user_similarity_df = pd.DataFrame(user_similarity, index=user_item_matrix.index, columns=user_item_matrix.index)
    
    # 3. Ambil pengguna yang mirip dengan pengguna target (kecuali dirinya sendiri)
    similar_users = user_similarity_df[user_id].sort_values(ascending=False)[1:]
    if similar_users.empty:
        return {}
        
    # 4. Hitung skor rekomendasi berdasarkan interaksi pengguna mirip
    weighted_interactions = user_item_matrix.loc[similar_users.index].multiply(similar_users.values, axis=0)
    recommendation_scores = weighted_interactions.sum(axis=0)

    # 5. Normalisasi skor ke rentang 0-1 agar bisa digabung
    scaler = MinMaxScaler()
    normalized_scores = scaler.fit_transform(recommendation_scores.values.reshape(-1, 1))
    
    return {char_id: score[0] for char_id, score in zip(recommendation_scores.index, normalized_scores)}

async def get_recommendations(user_id: int, alpha: float = 0.5) -> list[str]:
    """
    [FUNGSI UTAMA HYBRID]
    Menggabungkan hasil content-based dan collaborative filtering.
    """
    all_interactions = await get_interaction_data()
    user_history = all_interactions[all_interactions["user_id"] == user_id]

    if user_history.empty:
        all_char_ids = list(WAIFU.keys())
        return random.sample(all_char_ids, min(len(all_char_ids), 3))

    # Dapatkan skor dari kedua metode
    content_scores = content_based_filtering(user_history, WAIFU)
    collab_scores = collaborative_filtering(user_id, all_interactions)

    # Gabungkan skor dengan bobot alpha
    final_scores = {}
    all_char_ids = set(content_scores.keys()) | set(collab_scores.keys())

    for char_id in all_char_ids:
        content_score = content_scores.get(char_id, 0.0)
        collab_score = collab_scores.get(char_id, 0.0)
        final_score = (alpha * content_score) + ((1 - alpha) * collab_score)
        final_scores[char_id] = final_score
    
    # Sisa logika tetap sama: prioritaskan karakter baru, fallback jika semua sudah dicoba
    all_sorted_recs = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)
    
    interacted_chars = set(user_history["character_id"].unique())
    new_recs_sorted = [(cid, s) for cid, s in all_sorted_recs if cid not in interacted_chars]
    
    if not new_recs_sorted:
        print(f"User {user_id}: Tidak ada rekomendasi baru, menampilkan ulang yang paling cocok (hybrid).")
        return [cid for cid, s in all_sorted_recs[:3]]
    else:
        print(f"User {user_id}: Menampilkan rekomendasi baru (hybrid).")
        return [cid for cid, s in new_recs_sorted[:3]]

