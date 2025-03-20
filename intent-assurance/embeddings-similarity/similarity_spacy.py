import pandas as pd
import numpy as np
import spacy
from spacy.matcher import PhraseMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import logging

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# Technical terms, synonyms, critical keywords and rule categories
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

TECHNICAL_PHRASES = [
    "web server", "transmission error", "receive errors", "high temperatures", "access to it with SSH",
    "ssh access", "network interface", "cpu usage", "cpu utilization", "cpu performance", "cpu load",
    "cpu allocation", "memory usage", "memory utilization", "memory performance", "memory load",
    "memory allocation", "network bandwidth", "network latency", "network throughput", "network packet",
    "network tx", "network rx", "hardware temperature", "fan speed", "hardware speed", "hardware metal",
    "system zombie", "system process", "system kernel", "system dpdk", "system ssh"
]

# Loading model and matcher
nlp = spacy.load("en_core_web_md")
matcher = PhraseMatcher(nlp.vocab)
patterns = [nlp.make_doc(text) for text in TECHNICAL_PHRASES]
matcher.add("TECHNICAL_PHRASES", patterns)


# Normalize text, expand synonyms, and filter out stopwords
def normalize_text(text):
    doc = nlp(text.lower())
    tokens = []

    # Find technical phrases
    matches = matcher(doc)
    for match_id, start, end in matches:
        span = doc[start:end]
        tokens.append(span.text.replace(' ', '_'))

    # Process individual tokens
    for token in doc:
        if token.is_punct:
            continue
        # Expand technical synonyms
        lemma = token.lemma_
        if lemma in TECHNICAL_SYNONYMS:
            tokens.extend(TECHNICAL_SYNONYMS[lemma])
        else:
            tokens.append(lemma)
    # Filter out stopwords, short tokens, and digits
    filtered_tokens = [
        token for token in tokens
        if not nlp.vocab[token].is_stop
        and len(token) > 2
        and not token.isdigit()
    ]
    return ' '.join(filtered_tokens)

# Categorize rules
def categorize_rule(rule_text):
    processed = normalize_text(rule_text)
    scores = {category: 0 for category in RULE_CATEGORIES}
    
    for word in processed.split():
        for category, keywords in RULE_CATEGORIES.items():
            if word in keywords:
                scores[category] += 1
                
    main_category = max(scores, key=scores.get)
    return main_category if scores[main_category] > 0 else 'other'

# Calculate criticality score
def calculate_criticality(text):
    score = 1.0
    for word, boost in CRITICAL_KEYWORDS.items():
        if word in text.lower():
            score *= boost
    return min(score, 5.0)



def load_and_prepare_rules(file_path):
    
    logger.info(f"Loading rules from: {file_path}")
    df = pd.read_csv(file_path)
    
    # Normalize text
    logger.info("Normalizing and expanding tokens...")
    df['processed'] = df['name'].apply(normalize_text)
    
    # Categorization
    logger.info("Categorization of rules...")
    df['category'] = df['name'].apply(categorize_rule)
    
    # Criticality score
    logger.info("Calculating criticality score...")
    df['criticality_score'] = df['name'].apply(calculate_criticality)
    return df


class HybridEncoder:
    def __init__(self):
        self.tfidf = TfidfVectorizer(max_features=5000)
        self.bert = SentenceTransformer('all-mpnet-base-v2')
        
    def fit_transform(self, texts):
        logger.info("Training model TF-IDF...")
        self.tfidf.fit(texts)

        logger.info("Generating BERT embeddings...")
        tfidf_emb = self.tfidf.transform(texts).toarray()
        bert_emb = self.bert.encode(
            texts, 
            show_progress_bar=True,
            batch_size=32,
            convert_to_numpy=True
        )
        
        return np.hstack([tfidf_emb, bert_emb])
    
    def transform(self, texts):
        tfidf_emb = self.tfidf.transform(texts).toarray()
        bert_emb = self.bert.encode(
            texts, 
            show_progress_bar=False,
            batch_size=32,
            convert_to_numpy=True
        )
        return np.hstack([tfidf_emb, bert_emb])



class RuleRecommender:
    def __init__(self, rules_df):
        self.rules_df = rules_df
        self.encoder = HybridEncoder()
        self.embeddings = self.encoder.fit_transform(rules_df['processed'].tolist())
        
    def recommend(self, query, min_score=0.3, category_filter=None):
        processed_query = normalize_text(query)
        logger.debug(f"Query processed: {processed_query}")
        
        if category_filter:
            filtered_df = self.rules_df[self.rules_df['category'] == category_filter]
        else:
            filtered_df = self.rules_df
            
        query_emb = self.encoder.transform([processed_query])
        rule_embs = self.embeddings[filtered_df.index]
    
        similarities = cosine_similarity(query_emb, rule_embs).flatten()
        
        boosted_scores = similarities * filtered_df['criticality_score'].values
        
        mask = boosted_scores >= min_score
        filtered_results = filtered_df[mask]
        filtered_scores = boosted_scores[mask]

        sorted_indices = np.argsort(filtered_scores)[::-1]
        
        return filtered_results.iloc[sorted_indices], filtered_scores[sorted_indices]

def explain_recommendation(query, rules, scores, min_score):

    if rules.empty:
        print(f"No recommendations above score threshold {min_score:.2f} for query: '{query}'")
        return
    
    """Explicación mejorada de resultados"""
    print(f"\n{'='*80}\nRecommendations above {min_score:.2f} for: '{query}'\n{'='*80}")
    
    for idx, (_, rule), score in zip(range(len(rules)), rules.iterrows(), scores):
        print(f"\n[Score: {score:.2f}] {rule['name']}")
        print(f"  Category: {rule['category'].upper()}")
        print(f"  Criticality: {rule['criticality_score']:.1f}x")
        print(f"  Rule Code: {rule['rule']}")
        
        query_terms = set(normalize_text(query).split())
        rule_terms = set(rule['processed'].split())
        matched_terms = query_terms & rule_terms
        
        if matched_terms:
            print("  Matching Terms:")
            for term in matched_terms:
                print(f"   - {term.replace('_', ' ')}")
        
        print("-"*80)

if __name__ == "__main__":

    RULES_FILE = 'similarity_spacy.csv'
    USER_QUERY = "I want to deploy a web server that has minimum 6 CPUs available, with no transmision error neither receive errors from network. Moreover, I don't want the server to have high temperatures and I must be able to access to it with SSH."
    THRESHOLD = 0.3
    
    try:
        rules_df = load_and_prepare_rules(RULES_FILE)
        
        recommender = RuleRecommender(rules_df)

        recommended_rules, scores = recommender.recommend(USER_QUERY, THRESHOLD)
        
        explain_recommendation(USER_QUERY, recommended_rules, scores, THRESHOLD)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise e