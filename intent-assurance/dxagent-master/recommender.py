import pandas as pd
import numpy as np
import json
import csv
import logging
from pathlib import Path
import spacy
from spacy.matcher import PhraseMatcher
from rank_bm25 import BM25Okapi

import re
import asyncio
import aiohttp
import time

import subprocess
import os

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NUM_RULES = 38
LLM_USAGE = 0.6
THRESHOLD = 0.4


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
INVERTED_TECHNICAL_SYNONYMS = invert_synonyms(load_json('aux/technical_synonyms.json'))

RULE_CATEGORIES = load_json('aux/rule_categories.json')

TECHNICAL_PHRASES = load_json('aux/technical_phrases.json')


class LlamaRecommender:
    def __init__(self, model):
        self.model = model
        with open('aux/ollamaContext.txt', 'r', encoding='utf-8') as file:
            self.context = file.read()

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
        
    def _parse_response(self, response_data):
        if not response_data:
            logger.error(f"Error in the response.")
            return None

        response = response_data.get('response', 'N/A')
        if response == 'N/A': 
            return np.zeros(NUM_RULES)
        
        logger.debug(f"Raw response:\n {response}")
        
        pattern = r"^r(3[0-8]|1[0-9]|2[0-9]|[1-9]):(0\.\d{1,2}|1\.00)$"
        matches = re.findall(pattern, response, flags=re.MULTILINE)

        scores_dict = {int(rule): float(score) for rule, score in matches}

        llama_scores = np.zeros(NUM_RULES)
        for rule_num, score in scores_dict.items():
            if 1 <= rule_num <= NUM_RULES:
                llama_scores[rule_num - 1] = score
        
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
        
        logger.info("Initializing BM25 corpus...")
        tokenized_corpus = [doc.split() for doc in self.rules_df['processed'].tolist()]
        self.bm25 = BM25Okapi(tokenized_corpus)

        self.use_ollama = use_ollama
        if self.use_ollama:
            self.ollama = LlamaRecommender("gemma3:27b-it-q4_K_M")

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
        
    async def recommend(self, query, min_score=0.4):

        if self.use_ollama:
            ollama_task = asyncio.create_task(self.ollama.recommend(query))

        processed_query = self._normalize_text(query)
        tokenized_query = processed_query.split()

        raw_bm25_scores = self.bm25.get_scores(tokenized_query)
        max_bm25_score = np.max(raw_bm25_scores)
        
        if max_bm25_score > 0:
            bm25_scores = raw_bm25_scores / max_bm25_score
        else:
            bm25_scores = raw_bm25_scores

        if self.use_ollama:
            try:
                llama_scores = await asyncio.wait_for(ollama_task, timeout=200)
            except asyncio.TimeoutError:
                logger.warning("Timeout reached. Using base scores")
                llama_scores = np.zeros(NUM_RULES)
                
            logger.info(f"Llama scores length: {len(llama_scores)} | BM25 scores length: {len(bm25_scores)}")
                
            if len(llama_scores) != len(bm25_scores):
                raise ValueError("llama_scores must have the same length as bm25_scores")
                

            combined_scores = (bm25_scores * (1 - LLM_USAGE)) + (llama_scores * LLM_USAGE)
        else:
            combined_scores = bm25_scores

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

        evaluation_file = 'evaluations/llama_06.csv'
        file_exists = Path(evaluation_file).exists()

        with open(evaluation_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(['query', 'rule_ids'])
            writer.writerow([query, rules_ids])

    def save_rules(self, recommended_rules):
        source_file = 'aux/rules.csv'
        destination_file = 'res/rules.csv'
        rules = []
        with open(source_file, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['id'] in set(recommended_rules['id']):
                    rules.append(row)

        if rules:
            with open(destination_file, 'w', newline='') as file:
                headers = ['name', 'path', 'severity', 'rule']
                writer = csv.DictWriter(file, fieldnames=headers)

                writer.writeheader()
                for rule in rules:
                    writer.writerow({
                        'name': rule['name'],
                        'path': rule['path'],
                        'severity': rule['severity'],
                        'rule': rule['rule']
                    })       
        else:
            logger.info("RULEs empty")


def deploy_to_providers(rules_file_path):
    """
    Simulates the orchestration and deployment of the recommended rules to multiple provider nodes using Docker containers.
    """
    logger.info("Starting deployment to providers...")
    
    # List of provider container names
    providers = ["provider_A", "provider_B", "provider_C"]
    kafka_address = "kafka:29092"  # Assuming Kafka is running in a container named 'kafka'
    
    for provider in providers:
        try:
            logger.info(f"[{provider}] Copying rules file to container...")
            subprocess.run(
                ["docker", "cp", rules_file_path, f"{provider}:/app/rules.csv"],
                check=True,
                capture_output=True
            )
            
            logger.info(f"[{provider}] Starting DxAgent...")
            
            subprocess.Popen(
                ["docker", "exec", "-d", provider, "python3", "dxagent.py", "start"]
            )
            
            logger.info(f"[{provider}] Deployment completed successfully.")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error deploying to {provider}: {e.stderr.decode()}")
        except Exception as e:
            logger.error(f"Unexpected error in {provider}: {e}")

        logger.info("Waiting 3 seconds for gNMI servers to start properly...")
        time.sleep(3)  # Wait for gNMI servers to start

        for provider in providers:
        try:
            logger.info(f"[{provider}] Initializing DxCollector with Kafka integration...")
            subprocess.Popen([
                "docker", "exec", "-d", 
                "-e", f"NODE_NAME={provider}", 
                "-e", f"KAFKA_BROKER={kafka_address}",
                provider, 
                "python3", "dxcollector.py", "-f", "json", "--kafka"
            ])
            logger.info(f"[{provider}] DxCollector started successfully with Kafka integration.")
            
        except Exception as e:
            logger.error(f"Error {provider}: {e}")


async def main():
    RULES_FILE = 'aux/rules.csv'
    USER_QUERY = input("Query: ")

    try:
        start_time = time.time()
        recommender = RuleRecommender(RULES_FILE, use_ollama=True)
        
        recommended_rules, scores = await recommender.recommend(USER_QUERY, THRESHOLD)
        
        recommender.explain_recommendation(USER_QUERY, recommended_rules, scores, THRESHOLD)

        recommender.save_rules(recommended_rules)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"Execution completed in {elapsed_time:.2f} seconds.")

        deploy_to_providers('res/rules.csv')

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(main())

    venv_python = os.path.join(os.getcwd(),"venv", "bin", "python3")

    # subprocess.run(
    #     ["sudo", venv_python, "dxagent", "start"],
    #     check=True
    # )