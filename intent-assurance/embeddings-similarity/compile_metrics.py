import csv
import pandas as pd
from pathlib import Path
import re
import logging

# Configuración del Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_training_data(training_file):
    """
    Carga el ground truth (training_data.csv) en un diccionario una sola vez
    para optimizar el proceso.
    """
    training_data = {}
    with open(training_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Extraemos las reglas esperadas y quitamos espacios por seguridad
            rule_string = row.get('rule_ids', '')
            if rule_string and rule_string != 'None':
                training_data[row['query']] = set(rule_string.split(';'))
            else:
                training_data[row['query']] = set()
    return training_data

def calculate_metrics_for_file(evaluation_file, training_data):
    """
    Compara las recomendaciones de un archivo específico contra el ground truth
    y devuelve Precisión, Recall y F1-Score.
    """
    total_true_positives = 0
    total_false_positives = 0
    total_false_negatives = 0

    with open(evaluation_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            query = row['query']
            rule_string = row.get('rule_ids', '')
            
            if rule_string and rule_string != 'None':
                recommended_rules = set(rule_string.split(';'))
            else:
                recommended_rules = set()

            if query in training_data:
                expected_rules = training_data[query]
                
                # Intersección y diferencias de conjuntos
                true_positives = len(recommended_rules & expected_rules)
                false_positives = len(recommended_rules - expected_rules)
                false_negatives = len(expected_rules - recommended_rules)

                total_true_positives += true_positives
                total_false_positives += false_positives
                total_false_negatives += false_negatives

    # Prevención de división por cero
    sum_tp_fp = total_true_positives + total_false_positives
    precision = (total_true_positives / sum_tp_fp) * 100 if sum_tp_fp > 0 else 0.0

    sum_tp_fn = total_true_positives + total_false_negatives
    recall = (total_true_positives / sum_tp_fn) * 100 if sum_tp_fn > 0 else 0.0

    sum_prec_rec = precision + recall
    f1_score = (2 * precision * recall / sum_prec_rec) if sum_prec_rec > 0 else 0.0

    return round(precision, 2), round(recall, 2), round(f1_score, 2)

def compile_all_results(training_file, eval_directory, output_summary_file):
    """
    Recorre todos los archivos CSV en el directorio, extrae métricas y genera
    una tabla resumen ordenada por F1-Score.
    """
    eval_dir = Path(eval_directory)
    if not eval_dir.exists() or not eval_dir.is_dir():
        logger.error(f"El directorio {eval_directory} no existe.")
        return

    logger.info("Cargando datos de entrenamiento (Ground Truth)...")
    training_data = load_training_data(training_file)

    results = []
    
    # Expresión regular para extraer modelo, peso y umbral del nombre del archivo
    # Ej: gemma3_27b-it-q4_K_M_w50_t40.csv
    pattern = re.compile(r"^(.*)_w(\d+)_t(\d+)\.csv$")

    logger.info(f"Escaneando archivos en {eval_directory}...")
    
    for eval_file in eval_dir.glob("*.csv"):
        match = pattern.match(eval_file.name)
        if match:
            model_name = match.group(1)
            weight_pct = int(match.group(2))
            threshold_pct = int(match.group(3))
            
            # Convertir de vuelta a formato decimal para la tabla (ej. 50 -> 0.5)
            ollama_weight = weight_pct / 100.0
            threshold = threshold_pct / 100.0

            # Calcular las métricas usando tu lógica
            precision, recall, f1 = calculate_metrics_for_file(eval_file, training_data)

            results.append({
                "Model": model_name,
                "Ollama_Weight (X)": ollama_weight,
                "Threshold": threshold,
                "Precision (%)": precision,
                "Recall (%)": recall,
                "F1-Score (%)": f1
            })

    if not results:
        logger.warning("No se encontraron archivos con el formato esperado (_wXX_tXX.csv).")
        return

    # Convertir a DataFrame para un manejo tabular elegante
    df_results = pd.DataFrame(results)

    # Ordenar los resultados para que la mejor configuración (mayor F1-Score) salga la primera
    df_results.sort_values(by=["F1-Score (%)", "Precision (%)"], ascending=[False, False], inplace=True)

    # Exportar la tabla resumen a un CSV
    df_results.to_csv(output_summary_file, index=False, encoding='utf-8')
    
    logger.info(f"\n¡Evaluación completa! Se han procesado {len(results)} configuraciones.")
    logger.info(f"El resumen se ha guardado en: {output_summary_file}\n")
    
    # Imprimir el Top 5 por consola para verlo al instante
    print("="*70)
    print(" TOP 5 MEJORES CONFIGURACIONES (Basado en F1-Score)")
    print("="*70)
    print(df_results.head(5).to_string(index=False))
    print("="*70)


if __name__ == "__main__":
    # Rutas relativas según la estructura de tu proyecto
    TRAINING_FILE = "data/training_data.csv"
    EVALUATIONS_DIR = "evaluations/grid_search/"
    OUTPUT_SUMMARY_FILE = "evaluations/final_metrics_summary.csv"

    compile_all_results(TRAINING_FILE, EVALUATIONS_DIR, OUTPUT_SUMMARY_FILE)