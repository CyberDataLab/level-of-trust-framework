import pandas as pd
import numpy as np
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import logging

# Logging
logging.basicConfig(level=logging.INFO)

# Loading model
nlp = spacy.load("en_core_web_md")

# 1. Mapeo de términos técnicos
TECHNICAL_SYNONYMS = {
    'compute': ['processing', 'capacity', 'throughput', 'calculation'],
    'network': ['bandwidth', 'latency', 'throughput', 'transmission', 'connectivity'],
    'memory': ['ram', 'swap', 'buffers', 'allocation', 'storage'],
    'speed': ['latency', 'throughput', 'performance', 'response'],
    'critical': ['emergency', 'severe', 'alert', 'danger'],
    'overload': ['saturation', 'maxout', 'overutilization']
}

RULE_CATEGORIES = {
    'cpu': ['cpu', 'processing', 'core', 'load', 'compute'],
    'memory': ['memory', 'swap', 'buffer', 'allocation', 'free'],
    'network': ['network', 'bandwidth', 'latency', 'packet', 'tx', 'rx'],
    'hardware': ['temperature', 'fan', 'speed', 'hardware', 'metal'],
    'system': ['zombie', 'process', 'kernel', 'dpdk', 'ssh']
}

CRITICAL_KEYWORDS = {
    'critical': 2.0,
    'emergency': 1.8,
    'overload': 1.7,
    'depleted': 1.6,
    'error': 1.5,
    'drop': 1.4,
    'exhausted': 1.3
}

# 2. Preprocesamiento mejorado
def _normalize_text(text):
    doc = nlp(text.lower())
    tokens = []
    for token in doc:
        # Saltar signos de puntuación
        if token.is_punct:
            continue
        # Expansión de sinónimos técnicos
        lemma = token.lemma_
        if lemma in TECHNICAL_SYNONYMS:
            tokens.extend(TECHNICAL_SYNONYMS[lemma])
        else:
            tokens.append(lemma)
    
    return ' '.join(tokens)

# 3. Categorización de reglas
def categorize_rule(rule_text):
    processed = _normalize_text(rule_text)
    scores = {category: 0 for category in RULE_CATEGORIES}
    
    for word in processed.split():
        for category, keywords in RULE_CATEGORIES.items():
            if word in keywords:
                scores[category] += 1
                
    main_category = max(scores, key=scores.get)
    return main_category if scores[main_category] > 0 else 'other'

# 4. Modelo híbrido
class HybridEncoder:
    def __init__(self):
        self.tfidf = TfidfVectorizer(max_features=5000)
        self.bert = SentenceTransformer('all-mpnet-base-v2')
        
    def fit_transform(self, texts):
        self.tfidf.fit(texts)
        tfidf_emb = self.tfidf.transform(texts).toarray()
        bert_emb = self.bert.encode(texts, show_progress_bar=False)
        return np.hstack([tfidf_emb, bert_emb])
    
    def transform(self, texts):
        tfidf_emb = self.tfidf.transform(texts).toarray()
        bert_emb = self.bert.encode(texts, show_progress_bar=False)
        return np.hstack([tfidf_emb, bert_emb])

# 5. Carga y preparación de datos
def load_and_prepare_rules(file_path):
    df = pd.read_csv(file_path)
    
    # Preprocesamiento
    df['processed'] = df['name'].apply(_normalize_text)
    
    # Categorización
    df['category'] = df['name'].apply(categorize_rule)
    
    # Puntuación de criticidad
    df['criticality_score'] = df['name'].apply(
        lambda x: max([CRITICAL_KEYWORDS.get(word, 1) 
                  for word in x.lower().split()] or 1)
    )
    return df

# 6. Sistema de recomendación
class RuleRecommender:
    def __init__(self, rules_df):
        self.rules_df = rules_df
        self.encoder = HybridEncoder()
        self.embeddings = self.encoder.fit_transform(rules_df['processed'].tolist())
        
    def recommend(self, query, top_n=5, category_filter=None):
        # Preprocesar consulta
        processed_query = _normalize_text(query)
        
        # Filtrar por categoría si se especifica
        if category_filter:
            filtered_df = self.rules_df[self.rules_df['category'] == category_filter]
        else:
            filtered_df = self.rules_df
            
        # Generar embeddings
        query_emb = self.encoder.transform([processed_query])
        rule_embs = self.embeddings[filtered_df.index]
        
        # Calcular similitud
        similarities = cosine_similarity(query_emb, rule_embs).flatten()
        
        # Aplicar boost de criticidad
        boosted_scores = similarities * filtered_df['criticality_score'].values
        
        # Obtener mejores resultados
        top_indices = np.argsort(boosted_scores)[-top_n:][::-1]
        results = filtered_df.iloc[top_indices]
        
        return results, boosted_scores[top_indices]

# 7. Explicación de resultados
def explain_recommendation(query, rules, scores):
    feature_names = recommender.encoder.tfidf.get_feature_names_out()
    
    print(f"\nRecommendations for: '{query}'\n")
    for idx, (_, rule), score in zip(range(len(rules)), rules.iterrows(), scores):
        print(f"[Score: {score:.2f}] {rule['name']}")
        print(f"Category: {rule['category'].upper()}")
        print(f"Criticality: {rule['criticality_score']:.1f}x")
        print(f"Rule Code: {rule['rule']}")
        
        # Explicación de términos clave
        query_terms = set(_normalize_text(query).split())
        rule_terms = set(rule['processed'].split())
        matched_terms = query_terms & rule_terms
        
        print("Matching Terms:", ", ".join(matched_terms) if matched_terms else "No direct term matches")
        print("\n" + "="*80 + "\n")

# Ejecución principal
if __name__ == "__main__":
    # Cargar reglas
    rules_df = load_and_prepare_rules('similarity_spacy.csv')
    
    # Inicializar recomendador
    recommender = RuleRecommender(rules_df)
    
    # Obtener consulta
    user_query = "I want to deploy a web server that has minimum 6 CPUs available, with no transmision error neither receive errors from network. Moreover, I don't want the server to have high temperatures and I must be able to access to it with SSH."
    
    # Obtener recomendaciones
    recommended_rules, scores = recommender.recommend(user_query, top_n=40)
    
    # Mostrar resultados
    explain_recommendation(user_query, recommended_rules, scores)