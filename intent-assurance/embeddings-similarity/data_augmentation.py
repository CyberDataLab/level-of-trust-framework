import pandas as pd
import random
from nltk.corpus import wordnet
from nltk import download

# Descargar recursos necesarios
download('wordnet')
download('omw-1.4')

def get_synonyms(word):
    synonyms = set()
    for syn in wordnet.synsets(word):
        for lemma in syn.lemmas():
            clean_lemma = lemma.name().replace('_', ' ').lower()
            if clean_lemma != word.lower():
                synonyms.add(clean_lemma)
    return list(synonyms)

def augment_query(query, num_variants=20):
    words = query.split()
    variants = set()
    for _ in range(num_variants * 3):
        new_words = words.copy()
        indices = list(range(len(words)))
        random.shuffle(indices)
        for i in indices:
            synonyms = get_synonyms(words[i])
            if synonyms:
                new_words[i] = random.choice(synonyms)
                break
        variants.add(" ".join(new_words))
        if len(variants) >= num_variants:
            break
    return list(variants)

# Cargar CSV original
df = pd.read_csv("data/training_data.csv")
augmented = []

for _, row in df.iterrows():
    variants = augment_query(row["query"])
    for v in variants:
        augmented.append({"query": v, "rule_ids": row["rule_ids"]})

augmented_df = pd.DataFrame(augmented)
full_df = pd.concat([df, augmented_df])
full_df.to_csv("data/augmented_data_20.csv", index=False)
