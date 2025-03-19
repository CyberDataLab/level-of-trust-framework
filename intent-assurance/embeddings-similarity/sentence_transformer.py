import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from termcolor import colored
import csv

# --------------------------
# 1. Cargar Reglas desde CSV
# --------------------------
rules_df = pd.read_csv("rules.csv")
rules = rules_df.to_dict('records')

# --------------------------
# 2. Clase HybridMatcher
# --------------------------
class HybridMatcher:
    def __init__(self, rules):
        self.rules = rules
        
        # Modelo Semántico
        self.semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
        self._build_semantic_index()
        
        # TF-IDF
        self.tfidf_vectorizer = TfidfVectorizer(stop_words='english')
        self._build_tfidf_matrix()
    
    def _build_semantic_index(self):
        # Generar embeddings para nombre + path
        texts = [f"{rule['name']} {rule['path']}" for rule in self.rules]
        self.embeddings = self.semantic_model.encode(texts, normalize_embeddings=True)
        
        # Índice FAISS
        self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
        self.index.add(self.embeddings)
    
    def _build_tfidf_matrix(self):
        corpus = [f"{rule['name']} {rule['path']}" for rule in self.rules]
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(corpus)
    
    def query(self, prompt, top_k=20, semantic_weight=0.7):
        # Búsqueda Semántica
        prompt_embedding = self.semantic_model.encode([prompt], normalize_embeddings=True)
        semantic_scores, semantic_indices = self.index.search(prompt_embedding, top_k*2)
        
        # Búsqueda TF-IDF
        prompt_tfidf = self.tfidf_vectorizer.transform([prompt])
        keyword_scores = prompt_tfidf.dot(self.tfidf_matrix.T).toarray()[0]
        
        # Combinar resultados
        combined = []
        for idx in semantic_indices[0]:
            score = (semantic_scores[0][idx] * semantic_weight) + \
                    (keyword_scores[idx] * (1 - semantic_weight))
            combined.append( (idx, score) )
        
        # Ordenar y seleccionar top-k
        combined.sort(key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, _ in combined[:top_k]]
        
        return [(self.rules[idx], combined[i][1]) for i, idx in enumerate(top_indices)]

# --------------------------
# 3. Ejemplo de Uso
# --------------------------
matcher = HybridMatcher(rules)



with open('prompts.csv', newline='', encoding='utf-8') as file:
    lector = csv.DictReader(file)
    prompts = [line['Prompt'] for line in lector] 

i = 1
for p in prompts:
    matches = matcher.query(p)
    print(colored(f"\nCaso {i}: {p}", "blue"))
    i += 1
    for rule, score in matches:
        print(f"- {rule['name']} (Score: {score:.2f})")

"""# Caso 1: Problemas de red
prompt_1 = "Make a TLA for the user Bob that allows him to use up to 500Mb of bandwidth for NextCloud"
matches_1 = matcher.query(prompt_1)

print(colored("\nCaso 1 - Problemas de Banda Ancha:", "blue"))
for rule, score in matches_1:
    print(f"- {rule['name']} (Score: {score:.2f})")

# Caso 2: Sobrecarga de recursos
prompt_2 = "Scale up the resources of any edge service which status is overloaded"
matches_2 = matcher.query(prompt_2)

print(colored("\nCaso 2 - Servicios Sobrecargados:", "green"))
for rule, score in matches_2:
    print(f"- {rule['name']} (Score: {score:.2f})")"""