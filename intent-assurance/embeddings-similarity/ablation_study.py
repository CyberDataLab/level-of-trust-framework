import pandas as pd
import numpy as np
import csv
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def load_ground_truth(training_file):
    """Carga los datos reales esperados (Ground Truth)."""
    truth = {}
    with open(training_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['rule_ids'] and row['rule_ids'] != 'None':
                truth[row['query']] = set(row['rule_ids'].split(';'))
            else:
                truth[row['query']] = set()
    return truth

def calculate_metrics(recommended_dict, ground_truth):
    """Calcula las métricas globales para un conjunto de recomendaciones."""
    tp, fp, fn = 0, 0, 0
    
    for query, expected in ground_truth.items():
        recommended = recommended_dict.get(query, set())
        tp += len(recommended & expected)
        fp += len(recommended - expected)
        fn += len(expected - recommended)
        
    precision = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0
    recall = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0
    
    return precision, recall, f1

def run_comprehensive_ablation_study(raw_dir, training_file, output_csv):
    raw_path = Path(raw_dir)
    ground_truth = load_ground_truth(training_file)
    
    # 1. Cargar el archivo base (BM25 y Keyword)
    baseline_file = raw_path / "baselines_raw_scores.csv"
    if not baseline_file.exists():
        logger.error(f"Falta el archivo base: {baseline_file}")
        return
        
    logger.info("Cargando baselines...")
    df_base = pd.read_csv(baseline_file)
    
    # 2. Definir espacio de búsqueda
    base_models = {
        'BERT (TF-IDF+BERT)': 'similarity_score',
        'BM25': 'bm25_score',
        'Keyword Matching': 'keyword_score'
    }
    llm_weights = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]
    thresholds = [0.3, 0.4, 0.5, 0.6, 0.7]
    
    results = []
    
    # 3. Buscar automáticamente todos los archivos LLM generados
    llm_files = [f for f in raw_path.glob('*_raw_scores.csv') if 'baselines' not in f.name]
    
    if not llm_files:
        logger.error(f"No se encontraron archivos de LLM en {raw_dir}")
        return
        
    logger.info(f"Se encontraron {len(llm_files)} modelos LLM para evaluar. Iniciando cruce masivo...\n")
    
    # 4. Iterar sobre cada modelo LLM encontrado
    for llm_file in llm_files:
        llm_model_name = llm_file.stem.replace('_raw_scores', '')
        logger.info(f"Procesando cruzamientos para: {llm_model_name}")
        
        df_llm = pd.read_csv(llm_file)
        
        # Verificar si existe la columna similarity_score en el archivo del LLM
        # Si no existe (porque exportaste BERT en otro lado), la ignoramos dinámicamente
        available_bases = {name: col for name, col in base_models.items() 
                           if col in df_base.columns or col in df_llm.columns}
                           
        df_merged = pd.merge(df_llm, df_base, on=['query', 'rule_id'], how='inner')
        
        for base_name, base_col in available_bases.items():
            for w in llm_weights:
                for t in thresholds:
                    
                    combined_scores = (df_merged[base_col] * (1.0 - w)) + (df_merged['ollama_score'] * w)
                    
                    mask = combined_scores >= t
                    df_filtered = df_merged[mask]
                    
                    recommendations = df_filtered.groupby('query')['rule_id'].apply(set).to_dict()
                    precision, recall, f1 = calculate_metrics(recommendations, ground_truth)
                    
                    # Nombres dinámicos reflejando el modelo exacto
                    if w == 0.0:
                        config_name = f"Solo {base_name}"
                    elif w == 1.0:
                        config_name = f"Solo LLM ({llm_model_name})"
                    else:
                        config_name = f"Híbrido ({int((1-w)*100)}% {base_name} + {int(w*100)}% {llm_model_name})"
                    
                    results.append({
                        'Configuración': config_name,
                        'Modelo Base': base_name,
                        'Modelo LLM': llm_model_name,
                        'Peso LLM': w,
                        'Threshold': t,
                        'Precision (%)': precision,
                        'Recall (%)': recall,
                        'F1-Score (%)': f1
                    })
                    
    # 5. Procesar y exportar resultados
    df_results = pd.DataFrame(results)
    
    # Como w=0.0 (Solo Base) se calcula repetidamente por cada LLM iterado, borramos duplicados
    df_results = df_results.drop_duplicates(subset=['Configuración', 'Threshold'])
    
    df_results_sorted = df_results.sort_values(by='F1-Score (%)', ascending=False)
    
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    df_results_sorted.to_csv(output_csv, sep=";", decimal=",", index=False, float_format='%.2f')
    
    pd.options.display.float_format = '{:.2f}'.format
    print("\n" + "="*110)
    print(" TOP 15 MEJORES COMBINACIONES (ESTUDIO DE ABLACIÓN COMPLETO) ".center(110, '='))
    print("="*110)
    print(df_results_sorted.head(15).to_string(index=False))
    print("\nEstudio completado. Resultados totales en:", output_csv)

if __name__ == "__main__":
    RAW_DIR = "evaluations/raw/"
    TRAINING_FILE = "data/training_data.csv"
    OUTPUT_CSV = "evaluations/ablation_study_results.csv"
    
    run_comprehensive_ablation_study(RAW_DIR, TRAINING_FILE, OUTPUT_CSV)