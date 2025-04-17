import json
from nltk.corpus import wordnet as wn

"""
First time using this script:
import nltk
nltk.download("wordnet")
"""

tech_terms = ["cpu", "RAM", "storage"]
result = {}

for term in tech_terms:
    synsets = wn.synsets(term)
    synonyms = set()
    for syn in synsets:
        for lemma in syn.lemmas():
            synonym = lemma.name().lower()
            synonyms.add(synonym)
    result[term] = list(synonyms)

# Guardar en JSON
with open("tech_synonyms.json", "w") as f:
    json.dump(result, f, indent=4)