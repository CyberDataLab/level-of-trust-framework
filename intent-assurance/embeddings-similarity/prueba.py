from ollama import Client
import numpy as np
import re

def _parse_response(response_data):
        if not response_data:
            
            return None

        response = response_data.get('response', 'N/A')
        if response == 'N/A': 
            return np.zeros(36)
        
        pattern = r"^r(3[0-3]|[12][0-9]|[1-9]):(0|1|0\.\d{1,2}|1\.00)$"
        matches = re.findall(pattern, response, flags=re.MULTILINE)

        scores_dict = {int(rule): float(score) for rule, score in matches}

        llama_scores = np.zeros(33)
        for rule_num, score in scores_dict.items():
            if 1 <= rule_num <= 33:
                llama_scores[rule_num - 1] = score
        
        return llama_scores

ollama = Client(
    host='http://localhost:11434',
)

with open('data/ollamaContext.txt', 'r', encoding='utf-8') as file:
    context = file.read()

prompt = (f"{context} {input("Query: ")}")

response = ollama.chat(model="Modelfile:latest", messages=[
            {
                'role': 'user',
                'content': context,
            },
        ])


print(response['message']['content'])



print("-------------------------------------------")


print(_parse_response(response))
