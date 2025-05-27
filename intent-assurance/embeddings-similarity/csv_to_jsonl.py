import csv
import json

def convert_csv_to_jsonl(csv_file, jsonl_file):
    with open(csv_file, 'r', encoding='utf-8') as csv_input, \
         open(jsonl_file, 'w', encoding='utf-8') as jsonl_output:
        
        reader = csv.DictReader(csv_input)
        
        for row in reader:
            # Procesar las rule_ids
            rules = [f"{rule_id.strip()}:1" for rule_id in row['rule_ids'].split(';')]
            formatted_response = ", ".join(rules)
            
            # Crear el objeto JSON
            json_obj = {
                "input": row['query'],
                "response": formatted_response
            }
            
            # Escribir en formato JSONL
            jsonl_output.write(json.dumps(json_obj, ensure_ascii=False) + '\n')

# Uso del script
convert_csv_to_jsonl('data/augmented_data_20.csv', 'data/training_data.jsonl')