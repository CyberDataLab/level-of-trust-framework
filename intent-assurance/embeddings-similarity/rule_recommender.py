import spacy
from spacy.matcher import Matcher
import csv
from typing import List, Dict, Tuple
import logging
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# Logging
logging.basicConfig(level=logging.INFO)

# Loading model
nlp = spacy.load('en_core_web_md')      # 'en_core_web_lg' for better embeddings

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


class SemanticEncoder:
    def __init__(self):
        self.tfidf = TfidfVectorizer()
        self.bert = SentenceTransformer('all-mpnet-base-v2')
    
    def fit_transform(self, texts):
        self.tfidf.fit(texts)
        tfidf_embeddings = self.tfidf.transform(texts).toarray()
        bert_embeddings = self.bert.encode(texts)
        return np.hstack([tfidf_embeddings, bert_embeddings])
    
    def transform(self, texts):
        tfidf_embeddings = self.tfidf.transform(texts).toarray()
        bert_embeddings = self.bert.encode(texts)
        return np.hstack([tfidf_embeddings, bert_embeddings])


class RuleRecommender:

    def __init__(self, rules_file:str):
        self.rules = self.load_rules(rules_file)
        self.matcher = Matcher(nlp.vocab)
        self._initialize_nlp_pipeline()
        self._prepare_matcher()

        self.encoder = SemanticEncoder()
        self.embeddings = self.encoder.fit_transform(self.rules['rule_name'].tolist())

    # Load rules from csv
    def load_rules(self, file: str) -> List[Dict]:

        rules = []
        with open(file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rules.append({
                    'rule_name' : row['Rule'],
                    'path' : row['Path'],
                    'rule_code' : row['Rule_code'],
                    'keywords' : [self._normalize_text(kw) for kw in row['Keywords'].split(',')],
                    'priority' : self._detect_priority(row['Rule'])
                })

        
        return rules
    
    # Convert to lower and lemmatization
    def _normalize_text(self, text) -> str:
        doc = nlp(text)
        return " ".join([
            token.lemma_.lower()
            for token in doc
            if not token.is_stop and not token.is_punct
        ])
    # Check rule priority
    def _detect_priority(self, rule_name:str) -> int:
        """if 'critical' in rule_name.lower(): return 3
        if 'warning' in rule_name.lower(): return 2
        return 1"""
        for keyword, value in CRITICAL_KEYWORDS.items():
            if keyword in rule_name.lower():
                return value
        return 1
    
    def _initialize_nlp_pipeline(self):
        config = {
            "overwrite_ents": True,
            "phrase_matcher_attr": "LEMMA"
        }

        nlp.add_pipe("entity_ruler", name="technical_ruler", before="ner")
        ruler = nlp.get_pipe("technical_ruler")

        patterns = [
            {"label": "COMPONENT", "pattern": [{"LOWER": {"IN": ["cpu", "memory", "fan", "sensor", "buffer", "disk"]}}]},
            {"label": "METRIC", "pattern": [{"LOWER": {"IN": ["high", "low", "peak", "critical", "max", "min", "maximum", "minimum"]}}]},
            {"label": "NETWORK", "pattern": [{"LOWER": {"IN": ["packet", "mtu", "rx", "tx", "receive", "transmission"]}}]}
        ]

        ruler.add_patterns(patterns)


    def _prepare_matcher(self):
        """for rule in self.rules:
            patterns = [nlp(kw) for kw in rule['keywords']]
            self.matcher.add(rule['rule_name'], patterns)"""
        for rule in self.rules:
            patterns = []
            for kw in rule['keywords']:
                tokens = nlp(kw)
                pattern = [{"LEMMA": token.lemma_.lower()} for token in tokens]
                patterns.append(pattern)

            self.matcher.add(rule['rule_name'], patterns)

    def process_prompt(self, text: str, top_n: int = 5) -> List[Tuple[str, float]]:
        try:
            doc = nlp(self._normalize_text(text))
            matches = self.matcher(doc)

            scores = defaultdict(float)
            for match_id, start, end in matches:
                rule_name = nlp.vocab.strings[match_id]
                rule = next(r for r in self.rules if r['rule_name'] == rule_name)
                scores[rule_name] += 0.7 * rule['priority']                 # Priority as 'critical', 'warning', etc.
                scores[rule_name] += 0.3 * (1.0 / len(rule['keywords']))    # Matching with entities

            return sorted(
                [(rule, score) for rule, score in scores.items()],
                key=lambda x: (-x[1], x[0])
            )[:top_n]
            
        except Exception as e:
            logging.error(f"Error processing prompt: {str(e)}")
            return []
        

if __name__ == '__main__':
    recommender = RuleRecommender('rule_recommender.csv')

    prompts = [
        "I want to deploy a web server that has minimum 6 CPUs available, with no transmision error neither receive errors from network. Moreover, I don't want the server to have high temperatures and I must be able to access to it with SSH."
    ]

    for prompt in prompts:
        results = recommender.process_prompt(prompt)
        print(f"Prompt: {prompt}")
        print("Recommended Rules:", results)
        print("-" * 80)