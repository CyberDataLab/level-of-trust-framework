import pandas as pd
import numpy as np
import json
import csv
import logging
import joblib
from pathlib import Path

import spacy
from spacy.matcher import PhraseMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer
from sentence_transformers import SentenceTransformer

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_json(file_path):
    """
    Load technical phrases from a JSON file and return as a list.
    """
    logger.info(f"Loading technical phrases from: {file_path}")
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


def load_queries_from_csv(file_path):
    """
    Carga las queries desde un archivo CSV y las devuelve como una lista.
    """
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
        self.bert = SentenceTransformer("stsb-roberta-large")
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


class RuleRecommender:
    def __init__(self, rules_file, model_dir="models"):
        self.nlp = spacy.load("en_core_web_md")
        self.matcher = PhraseMatcher(self.nlp.vocab)

        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)

        self.rules_df = self._load_and_prepare_rules(rules_file)
        self.encoder = HybridEncoder()
        self.embeddings = None
        self.classifier = None
        self.label_encoder = MultiLabelBinarizer()

        self._initialize_components()

    def _initialize_components(self):
        patterns = [self.nlp.make_doc(text) for text in TECHNICAL_PHRASES]
        self.matcher.add("TECHNICAL_PHRASES", patterns)

        self.embeddings = self.encoder.fit_transform(self.rules_df['processed'].tolist())

        model_path = self.model_dir / "trained_model.pkl"
        if model_path.exists():
            self._load_model(model_path)
        else:
            self.classifier = Pipeline([
                ('clf', OneVsRestClassifier(
                    LogisticRegression(max_iter=1000, class_weight='balanced')
                ))
            ])
            logger.info("Initialized new classifier model.")

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

    def _save_model(self):
        model_path = self.model_dir / "trained_model.pkl"
        joblib.dump({
            'classifier': self.classifier,
            'label_encoder': self.label_encoder
        }, model_path)

        logger.info(f"Model saved to: {model_path}")

    def _load_model(self, model_path):
        model_data = joblib.load(model_path)
        self.classifier = model_data['classifier']
        self.label_encoder = model_data['label_encoder']
        logger.info(f"Model loaded from: {model_path}")

    def _validate_training_data(self, rules_df, train_df):
        all_rules = set(rules_df['id'])
        invalid = set()

        for rules in train_df['rule_ids'].str.split(';'):
            for r in rules:
                if r not in all_rules:
                    invalid.add(r)

        if invalid:
            raise ValueError(f"Invalid rule IDs found in training data: {invalid}")

    def train(self, training_data_path, save_model=True):
        logger.info(f"Training model with data from: {training_data_path}")
        train_df = pd.read_csv(training_data_path)
        self._validate_training_data(self.rules_df, train_df)

        x = self.encoder.transform(train_df['query'].apply(self._normalize_text))
        y = self.label_encoder.fit_transform(train_df['rule_ids'].str.split(';'))

        self.classifier.fit(x, y)

        if save_model:
            self._save_model()

        logger.info("Model training completed.")

    def recommend(self, query, min_score=0.3, use_ml=True):
        processed_query = self._normalize_text(query)
        query_emb = self.encoder.transform([processed_query])

        # Calcular similitudes y aplicar máscara
        similarities = cosine_similarity(query_emb, self.embeddings).flatten()
        mask = similarities >= min_score

        # Crear DataFrame filtrado
        filtered_df = self.rules_df[mask].copy()
        scores_filtered = similarities[mask]  # Esto ya es un array numpy

        if use_ml and self.classifier:
            # Obtener scores ML solo para las reglas filtradas
            ml_probs = self.classifier.predict_proba(query_emb)
            ml_scores = pd.Series(ml_probs[0], index=self.rules_df.index)[mask].values  # Convertir a array numpy

            # Combinar scores
            combined_scores = ml_scores

            # Ordenar y retornar
            sorted_indices = np.argsort(combined_scores)[::-1]
            return filtered_df.iloc[sorted_indices], combined_scores[sorted_indices]

        # Ordenar sin ML
        sorted_indices = np.argsort(scores_filtered)[::-1]
        return filtered_df.iloc[sorted_indices], scores_filtered[sorted_indices]

    def explain_recommendation(self, query, rules, scores, min_score):
        if rules.empty:
            print(f"No recommendations above score threshold {min_score:.2f} for query: '{query}'")
            return

        print(f"\n{'='*80}\nRecommendations above {min_score:.2f} for: '{query}'\n{'='*80}")

        for idx, (_, rule), score in zip(range(len(rules)), rules.iterrows(), scores):
            print(f"\n[Score: {score:.2f}] {rule['name']}")
            print(f"  Category: {rule['category'].upper()}")
            print(f"  Rule Code: {rule['rule']}")

            query_terms = set(self._normalize_text(query).split())
            rule_terms = set(rule['processed'].split())
            matched_terms = query_terms & rule_terms

            if matched_terms:
                print("  Matching Terms:")
                for term in matched_terms:
                    print(f"   - {term.replace('_', ' ')}")

            print("-"*80)

    def evaluate(self, query, recommended_rules):
        rules_ids = ';'.join(recommended_rules['id'].astype(str)) if not recommended_rules.empty else 'None'

        evaluation_file = 'data/evaluation.csv'
        file_exists = Path(evaluation_file).exists()

        with open(evaluation_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(['query', 'rule_ids'])

            writer.writerow([query, rules_ids])

if __name__ == "__main__":

    RULES_FILE = 'data/rules.csv'
    USER_QUERY = load_queries_from_csv("data/training_data.csv")
    THRESHOLD = 0.3

    TRAINING_DATA = 'data/training_data.csv'
    
    try:
        recommender = RuleRecommender(RULES_FILE)
        
        #if Path(TRAINING_DATA).exists(): recommender.train(TRAINING_DATA)

        for query in USER_QUERY:
            recommended_rules, scores = recommender.recommend(query, THRESHOLD, use_ml=False)
            recommender.evaluate(query, recommended_rules)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise e