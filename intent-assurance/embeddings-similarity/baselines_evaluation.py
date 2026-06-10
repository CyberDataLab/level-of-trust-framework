import pandas as pd
import numpy as np
import csv
import logging
from pathlib import Path
import spacy
from rank_bm25 import BM25Okapi
import time

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaselineRecommender:
    def __init__(self, rules_file):
        # Cargamos el modelo ligero de spaCy para normalización rápida
        self.nlp = spacy.load("en_core_web_md")
        self.rules_df = self._load_and_prepare_rules(rules_file)
        
        # Inicializar BM25
        logger.info("Entrenando modelo BM25...")
        tokenized_corpus = [doc.split() for doc in self.rules_df['processed'].tolist()]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def _normalize_text(self, text):
        """
        Versión simplificada de tu normalizador para los baselines.
        Elimina puntuación, stop words y tokeniza.
        """
        doc = self.nlp(text.lower())
        tokens = [token.lemma_ for token in doc if not token.is_punct and not token.is_stop and len(token) > 2 and not token.is_digit]
        return ' '.join(tokens)

    def _load_and_prepare_rules(self, file_path):
        logger.info(f"Cargando reglas desde: {file_path}")
        df = pd.read_csv(file_path)
        df['processed'] = df['name'].apply(self._normalize_text)
        return df

    def recommend_bm25(self, query, threshold=0.4):
        """
        Recomendación usando BM25.
        Normalizamos las puntuaciones al rango [0, 1] para que el threshold funcione igual que en tu script original.
        """
        processed_query = self._normalize_text(query).split()
        scores = self.bm25.get_scores(processed_query)
        
        # Normalizar scores (BM25 no está acotado entre 0 y 1 por defecto)
        max_score = np.max(scores) if np.max(scores) > 0 else 1
        normalized_scores = scores / max_score

        mask = normalized_scores >= threshold
        filtered_df = self.rules_df[mask].copy()
        filtered_scores = normalized_scores[mask]

        sorted_indices = np.argsort(filtered_scores)[::-1]
        return filtered_df.iloc[sorted_indices], filtered_scores[sorted_indices]

    def recommend_keyword_matching(self, query, threshold=0.3):
        """
        Recomendación usando Keyword Matching (Similitud de Jaccard).
        Calcula la intersección de palabras entre la query y la regla.
        """
        query_terms = set(self._normalize_text(query).split())
        scores = np.zeros(len(self.rules_df))

        if not query_terms:
            return pd.DataFrame(), np.array([])

        for idx, rule_text in enumerate(self.rules_df['processed']):
            rule_terms = set(rule_text.split())
            if not rule_terms:
                continue
            
            # Coeficiente de Jaccard: (Intersección) / (Unión)
            intersection = len(query_terms & rule_terms)
            union = len(query_terms | rule_terms)
            scores[idx] = intersection / union

        mask = scores >= threshold
        filtered_df = self.rules_df[mask].copy()
        filtered_scores = scores[mask]

        sorted_indices = np.argsort(filtered_scores)[::-1]
        return filtered_df.iloc[sorted_indices], filtered_scores[sorted_indices]

    def evaluate(self, query, recommended_rules, file):
        """
        Guarda los resultados en el mismo formato que tu script original.
        """
        rules_ids = ';'.join(recommended_rules['id'].astype(str)) if not recommended_rules.empty else 'None'
        file_exists = Path(file).exists()

        Path(file).parent.mkdir(parents=True, exist_ok=True)

        with open(file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['query', 'rule_ids'])
            writer.writerow([query, rules_ids])


def load_queries_from_csv(file_path):
    queries = []
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            queries.append(row['query'])
    return queries

def main():
    RULES_FILE = 'data/rules.csv'
    USER_QUERY = load_queries_from_csv("data/training_data.csv")
    
    recommender = BaselineRecommender(RULES_FILE)

    # Configuración de los experimentos
    methods = ['bm25', 'keyword']
    thresholds = [0.2, 0.3, 0.4, 0.5, 0.6]

    for method in methods:
        for threshold in thresholds:
            start_time = time.time()
            evaluation_file = f"evaluations/baselines/{method}_{threshold}.csv"
            
            # Limpiar archivo si existe para una ejecución limpia
            if Path(evaluation_file).exists():
                Path(evaluation_file).unlink()

            logger.info(f"Ejecutando baseline -> {method.upper()} | Threshold -> {threshold}")

            for query in USER_QUERY:
                if method == 'bm25':
                    recommended_rules, scores = recommender.recommend_bm25(query, threshold)
                elif method == 'keyword':
                    recommended_rules, scores = recommender.recommend_keyword_matching(query, threshold)
                
                recommender.evaluate(query, recommended_rules, evaluation_file)

            elapsed_time = time.time() - start_time
            logger.info(f"Completado {method.upper()} (th={threshold}) en {elapsed_time:.2f} segundos.\n")

if __name__ == "__main__":
    main()