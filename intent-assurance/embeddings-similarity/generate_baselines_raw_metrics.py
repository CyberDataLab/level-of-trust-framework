import pandas as pd
import numpy as np
import csv
import logging
from pathlib import Path
import spacy
from rank_bm25 import BM25Okapi

# Configuración del Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaselineRawExporter:
    def __init__(self, rules_file):
        self.nlp = spacy.load("en_core_web_md")
        self.rules_df = self._load_and_prepare_rules(rules_file)
        
        # Inicializar BM25
        logger.info("Entrenando modelo BM25...")
        tokenized_corpus = [doc.split() for doc in self.rules_df['processed'].tolist()]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def _normalize_text(self, text):
        doc = self.nlp(text.lower())
        tokens = [token.lemma_ for token in doc if not token.is_punct and not token.is_stop and len(token) > 2 and not token.is_digit]
        return ' '.join(tokens)

    def _load_and_prepare_rules(self, file_path):
        df = pd.read_csv(file_path)
        df['processed'] = df['name'].apply(self._normalize_text)
        return df

    def get_all_scores(self, query):
        """
        Calcula las puntuaciones de todas las reglas para una query usando BM25 y Keyword.
        Retorna dos arrays numpy con las puntuaciones.
        """
        processed_query_str = self._normalize_text(query)
        processed_query_tokens = processed_query_str.split()
        
        # --- 1. Puntuaciones BM25 ---
        bm25_scores = self.bm25.get_scores(processed_query_tokens)
        max_bm25 = np.max(bm25_scores) if np.max(bm25_scores) > 0 else 1
        normalized_bm25 = bm25_scores / max_bm25  # Normalizar entre 0 y 1

        # --- 2. Puntuaciones Keyword Matching (Jaccard) ---
        query_terms = set(processed_query_tokens)
        keyword_scores = np.zeros(len(self.rules_df))
        
        if query_terms:
            for idx, rule_text in enumerate(self.rules_df['processed']):
                rule_terms = set(rule_text.split())
                if rule_terms:
                    intersection = len(query_terms & rule_terms)
                    union = len(query_terms | rule_terms)
                    keyword_scores[idx] = intersection / union

        return normalized_bm25, keyword_scores

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
    OUTPUT_FILE = 'evaluations/raw/baselines_raw_scores.csv'
    
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    exporter = BaselineRawExporter(RULES_FILE)
    
    logger.info("Calculando puntuaciones en bruto para los baselines...")
    
    # Escribir los resultados en bruto
    with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['query', 'rule_id', 'bm25_score', 'keyword_score'])
        
        for query in USER_QUERY:
            bm25_scores, keyword_scores = exporter.get_all_scores(query)
            
            # Guardar una fila por cada regla
            for idx, rule_id in enumerate(exporter.rules_df['id']):
                # Se formatea a 4 decimales para mayor limpieza
                writer.writerow([
                    query, 
                    rule_id, 
                    f"{bm25_scores[idx]:.4f}", 
                    f"{keyword_scores[idx]:.4f}"
                ])
                
    logger.info(f"¡Exportación completada! Archivo guardado en: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()