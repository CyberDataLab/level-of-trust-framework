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
import requests
import asyncio
import aiohttp

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

def invert_synonyms(synonyms):
    inverted = {}
    for key, values in synonyms.items():
        for synonym in [key] + values:  # Incluye la clave y sus sinónimos
            inverted[synonym] = [key] + values
    return inverted

# Technical terms, synonyms, critical keywords and rule categories
INVERTED_TECHNICAL_SYNONYMS = invert_synonyms(load_json('data/technical_synonyms.json'))

RULE_CATEGORIES = load_json('data/rule_categories.json')

TECHNICAL_PHRASES = load_json('data/technical_phrases.json')

"""CRITICAL_KEYWORDS = {
    'critical': 2.0,
    'emergency': 1.8,
    'overload': 1.7,
    'depleted': 1.6,
    'error': 1.5,
    'drop': 1.4,
    'exhausted': 1.3
}"""
CRITICAL_KEYWORDS = {}


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
        """tfidf_emb = self.tfidf.transform(texts).toarray()
        bert_emb = self.bert.encode(
            texts, 
            show_progress_bar=False,
            batch_size=32,
            convert_to_numpy=True
        )
        return np.hstack([tfidf_emb, bert_emb])"""
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
        self.context = ("You are an expert system administrator with a system resource monitoring application. "
                    "For this, you have the following rules that you can apply. \n"
                    "id,name,rule\n"
                    "r1,Bare Metal Memory Underutilized (Free more than 50%),free>50\n"
                    "r2,Bare Metal CPU Underutilized (Idle more than 90%),idle_time>90\n"
                    "r3,Virtual Machine CPU Underutilized (Idle more than 90%),idle_time>90\n"
                    "r4,Bare Metal Swap Usage Active (Swap Used more than 0),swap_used!=0\n"
                    "r5,Bare Metal Memory Exhausted (Free less than 50%),free<50\n"
                    "r6,Bare Metal Critical Memory Exhaustion (Free less than 50% for 1 min),1min(free)<50\n"
                    "r7,Virtual Machine Memory Exhausted (Free less than 50%),free<50\n"
                    "r8,Virtual Machine Critical Memory Exhaustion (Free less than 50% for 1min),1min(free)<50\n"
                    "r9,Bare Metal Hugepages Depleted (Pages Free = 0),pages_free==0\n"
                    "r10,Bare Metal CPU Overloaded (Idle less or equal than 1% for 1min),1min(idle_time)<=1\n"
                    "r11,Bare Metal CPU Critical Overload (Idle less or equal than 1% for 5min),5min(idle_time)<=1\n"
                    "r12,Virtual Machine CPU Overloaded (Idle less or equal than 1% for 1min),1min(idle_time)<=1\n"
                    "r13,Virtual Machine CPU Critical Overload (Idle less or equal than 1% for 5min),5min(idle_time)<=1\n"
                    "r14,Bare Metal Temperature Limit Reached (Temperature more or equal than Max temperature),input_temp>=max_temp\n"
                    "r15,Bare Metal Critical Temperature Alert (Temperature more or equal than Critical),input_temp>=critical_temp\n"
                    "r16,Bare Metal Critical Fan Speed (Speed less than 100 RPM),input_fanspeed<100\n"
                    "r17,Bare Metal Zombie Processes Active (Count more than 0),zombie_count>0\n"
                    "r18,Virtual Machine SSH Access Down,ssh==0\n"
                    "r19,Bare Metal Network Critical: Default Gateway ARP Missing,(state==""up"") and (gw_in_arp==0)\n"
                    "r20,Bare Metal Network Non-Standard MTU,(mtu!=1500) and (type==ether)\n"
                    "r21,Bare Metal Network Interface Flapping (Changes more than 6 per min),1min(dynamicity(changes_count))>=6\n"
                    "r22,Bare Metal Network High Rx Errors (Errors more than 100 per min),1min(dynamicity(rx_error))>100\n"
                    "r23,Bare Metal Network High Rx Packet Drops (Rx Drops more than 10k per 1min),1min(dynamicity(rx_drop))>10000\n"
                    "r24,Bare Metal Network High Tx Errors (Errors more than 100 per min),1min(dynamicity(tx_error))>100\n"
                    "r25,Bare Metal Network High Tx Packet Loss (Tx Drops more than 100 per 1min),1min(dynamicity(tx_drop))>100\n"
                    "r26,Kernel/DPDK Network GSO Buffer Starvation,dynamicity(gso_no_buffers)>0\n"
                    "r27,Kernel/DPDK Network Mbuf Depletion (Drops more than 0),dynamicity(rx_no_buffer)>0\n"
                    "r28,Kernel/DPDK Network IP4 Input Buffer Missing,dynamicity(ip4_input_out_of_buffers)>0\n"
                    "r29,Kernel/DPDK Network Excessive IP Fragments,dynamicity(ip4_input_fragment_chain_too_long)>0\n"
                    "r30,Kernel/DPDK Network IP4 Destination Miss,dynamicity(ip4_input_destination_lookup_miss)>0\n"
                    "r31,Kernel/DPDK Network High Rx Errors,1min(dynamicity(rx_error))>100\n"
                    "r32,Kernel/DPDK Network High Rx Packet Drops,1min(dynamicity(rx_drop))>10000\n"
                    "r33,Kernel/DPDK Network High Tx Errors,1min(dynamicity(tx_error))>100\n"
                    "r34,Kernel/DPDK Network High Tx Packet Loss,1min(dynamicity(tx_drop))>100\n"
                    "r35,Kernel/DPDK Memory Low Buffers,(buffer_free/buffer_total)<0.1\n"
                    "r36,Kernel/DPDK Network DPDK Buffer Allocation Errors,dynamicity(dpdk_alloc_errors)>0\n"
                    "I need you to indicate a score for every rule in the system."
                 #   "I need you to indicate me for each rule, its percentage of success for the specific query of the user. \n"
                    "You must mention every rule.\n"
                    "The format I want you to do is: 'id:(0-1)'.\n"
                    "For example: r1:0.32 and so on with every rule \n"
                    "Just indicate the id and the percentage, don't show any more. If there is no rule applicable, show None"
                    "The query is the following: ")

    async def _send_request(self, session, prompt, stream=False):
        url = "http://localhost:11434/api/generate"
        try:
            data = {"model": self.model, "prompt": prompt, "stream": stream}
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            logger.error(f"Error in the request: {e}")
            return None
        
        """data = {"model": self.model, "prompt": prompt, "stream": stream}
        response = requests.post(url, json=data)
        return response.json() if response.status_code == 200 else None"""
    
    def _parse_response(self, response_data):
        if not response_data:
            return "Error en la respuesta del modelo"

        response = response_data.get('response', 'N/A')
        if response == 'N/A': 
            return np.zeros(36)
        
        with open('response_llama.txt', 'w') as file:
                 file.write(str(response))
        
        pattern = r"^r(3[0-6]|1[0-9]|2[0-9]|[1-9]):(0\.\d{2}|1\.00)$"
        matches = re.findall(pattern, response, flags=re.MULTILINE)

        scores_dict = {int(rule): float(score) for rule, score in matches}

        llama_scores = np.zeros(36)
        for rule_num, score in scores_dict.items():
            if 1 <= rule_num <= 36:
                llama_scores[rule_num - 1] = score

        with open('response_parsed.txt', 'w') as file:
            file.write(str(llama_scores))


        return llama_scores
        
    
    async def recommend(self, query):
        prompt = (f"{self.context} {query}")
        logger.info("Sending query to ollama.")
        async with aiohttp.ClientSession() as session:
            response_data = await self._send_request(session, prompt)
            logger.info("Parsing response from ollama.")
            return self._parse_response(response_data)


class RuleRecommender:
    def __init__(self, rules_file, use_ollama = False):

        self.nlp = spacy.load("en_core_web_md")
        self.matcher = PhraseMatcher(self.nlp.vocab)
        patterns = [self.nlp.make_doc(text) for text in TECHNICAL_PHRASES]
        self.matcher.add("TECHNICAL_PHRASES", patterns)

        self.rules_df = self._load_and_prepare_rules(rules_file)
        self.encoder = HybridEncoder()
        self.embeddings = self.encoder.fit_transform(self.rules_df['processed'].tolist())

        self.use_ollama = use_ollama
        if self.use_ollama:
            self.ollama = LlamaRecommender("gemma3:1b")


    
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
            # Expand technical synonyms
            lemma = token.lemma_

            """ O(n) every time a token is processed
                o(1) when creating the dictionary
            synonyms_found = False
            for key, synonyms in TECHNICAL_SYNONYMS.items():
                if lemma == key or lemma in synonyms:
                    tokens.extend([key] + synonyms)  # Añade la clave y todos los sinónimos
                    synonyms_found = True
                    break
            if not synonyms_found:
                tokens.append(lemma)
            """

            # O(1) every time a token is processed
            # O(n) when creating invert dictionary
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

    # Calculate criticality score
    def _calculate_criticality(self, text):
        score = 1.0
        for word, boost in CRITICAL_KEYWORDS.items():
            if word in text.lower():
                score *= boost
        return min(score, 5.0)

    def _load_and_prepare_rules(self, file_path):
        
        logger.info(f"Loading rules from: {file_path}")
        df = pd.read_csv(file_path)
        
        # Normalize text
        logger.info("Normalizing and expanding tokens...")
        df['processed'] = df['name'].apply(self._normalize_text)
        
        # Categorization
        logger.info("Categorization of rules...")
        df['category'] = df['name'].apply(self._categorize_rule)
        
        # Criticality score
        logger.info("Calculating criticality score...")
        df['criticality_score'] = df['name'].apply(self._calculate_criticality)
        return df
        
    async def recommend(self, query, min_score=0.3):

        if self.use_ollama:
            ollama_task = asyncio.create_task(self.ollama.recommend(query))

        processed_query = self._normalize_text(query)
        query_emb = self.encoder.transform([processed_query])

        # Calcular similitudes y aplicar máscara
        similarities = cosine_similarity(query_emb, self.embeddings).flatten()
        boosted_scores = similarities * self.rules_df['criticality_score'].values
        mask = boosted_scores >= min_score
        
        # Crear DataFrame filtrado con índices originales preservados
        processed_query = self._normalize_text(query)
        query_emb = self.encoder.transform([processed_query])

        # Calcular similitudes y aplicar máscara
        similarities = cosine_similarity(query_emb, self.embeddings).flatten()
        boosted_scores = similarities * self.rules_df['criticality_score'].values

        with open('cosine.txt', 'w') as file:
            file.write(str(boosted_scores))
        
        if self.use_ollama:

            try:
                llama_scores = await asyncio.wait_for(ollama_task, timeout=200)
            except asyncio.TimeoutError:
                logger.warning("Timeout reached. Using base scores")
                llama_scores = np.zeros(36)
                
            if len(llama_scores) != len(boosted_scores):
                raise ValueError("llama_scores must have the same length than cosine similarity")
            combined_scores = boosted_scores * 0.5 + llama_scores * 0.5
        else:
            combined_scores = boosted_scores

        mask = combined_scores >= min_score
        filtered_df = self.rules_df[mask].copy()
        filtered_scores = combined_scores[mask]

        sorted_indices = np.argsort(filtered_scores)[::-1]
        return filtered_df.iloc[sorted_indices], filtered_scores[sorted_indices]

    def explain_recommendation(self, query, rules, scores, min_score):

        if rules.empty:
            print(f"No recommendations above score threshold {min_score:.2f} for query: '{query}'")
            return
        
        print(f"\n{'='*80}\nRecommendations above {min_score:.2f} for: '{query}'\n{'='*80}")
        
        for idx, (_, rule), score in zip(range(len(rules)), rules.iterrows(), scores):
            print(f"\n[Score: {score:.2f}] {rule['name']}")
            print(f"  Category: {rule['category'].upper()}")
            print(f"  Criticality: {rule['criticality_score']:.1f}x")
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

        evaluation_file = 'data/evaluation_augmented.csv'
        file_exists = Path(evaluation_file).exists()

        # Escribir en el archivo CSV
        with open(evaluation_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            # Escribir encabezados si el archivo no existe
            if not file_exists:
                writer.writerow(['query', 'rules_id'])
            # Escribir la fila con la query y las reglas asociadas
            writer.writerow([query, rules_ids])

async def main():
    RULES_FILE = 'data/rules.csv'
    USER_QUERY = "I need a web server with guaranteed CPU availability and no network packet loss"
    #USER_QUERY = "I want to deploy a web server that has minimum 6CPUs available"
    #USER_QUERY = load_json("data/queries.json")
    THRESHOLD = 0

    TRAINING_DATA = 'data/augmented_training_data_gpt.csv'
    
    try:
        recommender = RuleRecommender(RULES_FILE, True)
        
        recommended_rules, scores = await recommender.recommend(USER_QUERY, THRESHOLD)
        
        recommender.explain_recommendation(USER_QUERY, recommended_rules, scores, THRESHOLD)

        """for query in USER_QUERY:
            recommended_rules, scores = recommender.recommend(query, THRESHOLD)
            recommender.evaluate(query, recommended_rules)"""

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())
    