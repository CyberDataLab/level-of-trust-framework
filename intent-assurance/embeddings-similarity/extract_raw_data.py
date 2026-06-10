import pandas as pd
import numpy as np
import json
import csv
import logging
from pathlib import Path
import spacy
from spacy.matcher import PhraseMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

import re
import asyncio
import aiohttp
import time

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BERT = "stsb-roberta-large"

def load_json(file_path):
    """
    Load technical phrases from a JSON file and return as a list.
    """
    logger.info(f"Loading technical phrases from: {file_path}")
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def load_queries_from_csv(file_path):
    queries = []
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            queries.append(row['query'])
    return queries

def invert_synonyms(synonyms):
    inverted = {}
    for key, values in synonyms.items():
        for synonym in [key] + values:  
            inverted[synonym] = [key] + values
    return inverted

# Technical terms, synonyms, critical keywords and rule categories
INVERTED_TECHNICAL_SYNONYMS = invert_synonyms(load_json('data/technical_synonyms.json'))
RULE_CATEGORIES = load_json('data/rule_categories.json')
TECHNICAL_PHRASES = load_json('data/technical_phrases.json')

class HybridEncoder:
    def __init__(self):
        self.tfidf = TfidfVectorizer(max_features=5000)
        self.bert = SentenceTransformer(BERT)
        self._cache = {}
        
    def fit_transform(self, texts):
        logger.info("Training model TF-IDF...")
        self.tfidf.fit(texts)

        logger.info("Generating BERT embeddings...")
        tfidf_emb = self.tfidf.transform(texts).toarray()
        bert_emb = self.bert.encode(
            texts, 
            show_progress_bar=True,
            batch_size=64,
            convert_to_numpy=True
        )
        
        return np.hstack([tfidf_emb, bert_emb])
    
    def transform(self, texts):
        cached = [self._cache.get(text, None) for text in texts]
        to_process = [text for text, emb in zip(texts, cached) if emb is None]
        
        if to_process:
            new_tfidf = self.tfidf.transform(to_process).toarray()
            new_bert = self.bert.encode(
                to_process,
                show_progress_bar=False,
                batch_size=64,
                convert_to_numpy=True
            )
            new_embs = np.hstack([new_tfidf, new_bert])

            for text,emb in zip(to_process, new_embs):
                self._cache[text] = emb

        return np.array(
            [self._cache[text] if emb is None else emb
             for text, emb in zip(texts, cached)]
        )

class LlamaRecommender:
    def __init__(self, model):
        self.model = model
        with open('data/ollamaContext.txt', 'r', encoding='utf-8') as file:
            self.context = file.read()

    async def _send_request(self, session, prompt, stream=False):
        url = "http://localhost:11434/api/generate"
        try:
            data = {"model": self.model, "prompt": prompt, "stream": stream, "options": { "temperature": 0 }}
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            logger.error(f"Error in the request: {e}")
            return None
        
    def _parse_response(self, response_data):
        if not response_data:
            logger.error(f"Error in the response.")
            return None

        response = response_data.get('response', 'N/A')
        if response == 'N/A': 
            return np.zeros(33)
        
        pattern = r"^r(3[0-6]|1[0-9]|2[0-9]|[1-9]):(0\.\d{1,2}|1\.00)$"
        matches = re.findall(pattern, response, flags=re.MULTILINE)

        scores_dict = {int(rule): float(score) for rule, score in matches}

        # Asegúrate de que el tamaño coincida con la cantidad máxima de reglas (33)
        llama_scores = np.zeros(33) 
        for rule_num, score in scores_dict.items():
            if 1 <= rule_num <= 33:
                llama_scores[rule_num - 1] = score
        
        return llama_scores
        
    async def recommend(self, query):
        prompt = (f"{self.context} {query}")
        async with aiohttp.ClientSession() as session:
            response_data = await self._send_request(session, prompt)
            return self._parse_response(response_data)


class RuleRecommender:
    def __init__(self, rules_file, llm_model, use_ollama=False):
        self.llm_model = llm_model
        self.nlp = spacy.load("en_core_web_md")
        self.matcher = PhraseMatcher(self.nlp.vocab)
        patterns = [self.nlp.make_doc(text) for text in TECHNICAL_PHRASES]
        self.matcher.add("TECHNICAL_PHRASES", patterns)

        self.rules_df = self._load_and_prepare_rules(rules_file)
        self.encoder = HybridEncoder()
        self.embeddings = self.encoder.fit_transform(self.rules_df['processed'].tolist())

        self.use_ollama = use_ollama
        if self.use_ollama:
            self.ollama = LlamaRecommender(self.llm_model)

    def _normalize_text(self, text):
        doc = self.nlp(text.lower())
        tokens = []

        # Find technical phrases
        matches = self.matcher(doc)
        for match_id, start, end in matches:
            span = doc[start:end]
            tokens.append(span.text.replace(' ', '_'))

        # Process individual tokens
        for token in doc:
            if token.is_punct:
                continue
            
            lemma = token.lemma_
            if lemma in INVERTED_TECHNICAL_SYNONYMS:
                tokens.extend(INVERTED_TECHNICAL_SYNONYMS[lemma])
            else:
                tokens.append(lemma)

        # Filter out stopwords, short tokens, and digits
        filtered_tokens = [
            token for token in tokens
            if not self.nlp.vocab[token].is_stop
            and len(token) > 2
            and not token.isdigit()
        ]
        return ' '.join(filtered_tokens)
    
    # Categorize rules
    def _categorize_rule(self, rule_text):
        processed = self._normalize_text(rule_text)
        scores = {category: 0 for category in RULE_CATEGORIES}
        
        for word in processed.split():
            for category, keywords in RULE_CATEGORIES.items():
                if word in keywords:
                    scores[category] += 1
                    
        main_category = max(scores, key=scores.get)
        return main_category if scores[main_category] > 0 else 'other'

    def _load_and_prepare_rules(self, file_path):
        logger.info(f"Loading rules from: {file_path}")
        df = pd.read_csv(file_path)
        
        # Normalize text
        logger.info("Normalizing and expanding tokens...")
        df['processed'] = df['name'].apply(self._normalize_text)
        
        # Categorization
        logger.info("Categorization of rules...")
        df['category'] = df['name'].apply(self._categorize_rule)
        
        return df
        
    async def get_raw_scores(self, query):
        """
        Calcula y devuelve las puntuaciones en bruto de similitud y de Ollama.
        """
        if self.use_ollama:
            ollama_task = asyncio.create_task(self.ollama.recommend(query))

        processed_query = self._normalize_text(query)
        query_emb = self.encoder.transform([processed_query])

        # Calculate similarity
        similarities = cosine_similarity(query_emb, self.embeddings).flatten()

        if self.use_ollama:
            try:
                llama_scores = await asyncio.wait_for(ollama_task, timeout=200)
            except asyncio.TimeoutError:
                logger.warning("Timeout reached. Using base scores of 0.")
                llama_scores = np.zeros(len(similarities))
                
            # Evitar fallos si las dimensiones no coinciden por alguna razón
            if llama_scores is None:
                llama_scores = np.zeros(len(similarities))
            elif len(llama_scores) != len(similarities):
                logger.warning(f"Dimension mismatch: llama({len(llama_scores)}) vs sim({len(similarities)}). Resizing.")
                llama_scores = np.resize(llama_scores, len(similarities))
        else:
            llama_scores = np.zeros(len(similarities))

        return self.rules_df, similarities, llama_scores

    def export_raw_scores(self, query, rules_df, similarities, llama_scores, file_path):
        """
        Guarda las puntuaciones sin procesar en un archivo CSV.
        """
        file_path = Path(file_path)
        # Asegurar que el directorio existe
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = file_path.exists()

        with open(file_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Inicializar cabeceras si el archivo no existe
            if not file_exists:
                writer.writerow(['query', 'rule_id', 'similarity_score', 'ollama_score'])
            
            # Escribir una fila por cada regla evaluada
            for idx, row in rules_df.iterrows():
                writer.writerow([
                    query, 
                    row['id'], 
                    round(float(similarities[idx]), 4), 
                    round(float(llama_scores[idx]), 4)
                ])

MODELS = ["gemma3:27b-it-q4_K_M", "gemma3:27b-it-q8_0"]

async def main():
    RULES_FILE = 'data/rules.csv'
    USER_QUERY = load_queries_from_csv("data/training_data.csv")
    
    try:
        for model in MODELS:
            start_time = time.time()
            recommender = RuleRecommender(RULES_FILE, llm_model=model, use_ollama=True)

            # Archivo maestro para guardar los raw scores
            sanitized_model_name = model.replace(":", "_")
            raw_data_file = Path(f"evaluations/raw/{sanitized_model_name}_raw_scores.csv")
            
            logger.info(f"Using model -> {model}. Saving raw data to: {raw_data_file}")
            
            # Eliminar archivo de ejecuciones previas para no duplicar datos
            if raw_data_file.exists():
                raw_data_file.unlink()

            for query in USER_QUERY:
                # 1. Obtener puntuaciones
                rules_df, similarities, llama_scores = await recommender.get_raw_scores(query)
                
                # 2. Guardar puntuaciones
                recommender.export_raw_scores(query, rules_df, similarities, llama_scores, raw_data_file)
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            logger.info(f"Execution completed in {elapsed_time:.2f} seconds. MODEL = {model}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())