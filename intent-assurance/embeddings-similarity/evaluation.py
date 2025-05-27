import csv

def evaluate_system(training_file, evaluation_file):
    # Cargar training_data.csv en un diccionario
    training_data = {}
    with open(training_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            training_data[row['query']] = set(row['rule_ids'].split(';'))

    # Inicializar variables para el cálculo de métricas
    total_true_positives = 0
    total_false_positives = 0
    total_false_negatives = 0

    # Leer evaluation.csv y comparar con training_data
    with open(evaluation_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            query = row['query']
            recommended_rules = set(row['rule_ids'].split(';')) if row['rule_ids'] != 'None' else set()

            # Verificar si la query existe en training_data
            if query in training_data:
                expected_rules = training_data[query]
                true_positives = len(recommended_rules & expected_rules)  # Reglas correctas recomendadas
                false_positives = len(recommended_rules - expected_rules)  # Reglas recomendadas de más
                false_negatives = len(expected_rules - recommended_rules)  # Reglas esperadas no recomendadas

                total_true_positives += true_positives
                total_false_positives += false_positives
                total_false_negatives += false_negatives

    # Calcular precisión, recall y F1-score
    precision = (total_true_positives / (total_true_positives + total_false_positives)) * 100 if (total_true_positives + total_false_positives) > 0 else 0
    recall = (total_true_positives / (total_true_positives + total_false_negatives)) * 100 if (total_true_positives + total_false_negatives) > 0 else 0
    f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0

    # Imprimir resultados
    print(f"Precisión: {precision:.2f}%")
    print(f"Recall: {recall:.2f}%")
    print(f"F1-score: {f1_score:.2f}%")

# Archivos de entrada
training_file = 'data/training_data.csv'
evaluation_file = 'evaluations/deberta-01.csv'



# Ejecutar la evaluación
evaluate_system(training_file, evaluation_file)

