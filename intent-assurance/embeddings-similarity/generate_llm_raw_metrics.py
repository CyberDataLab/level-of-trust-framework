import pandas as pd
from pathlib import Path
import logging

# Configuración del Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def evaluate_grid_search(raw_scores_path, output_dir, weights, thresholds):
    """
    Lee las puntuaciones en bruto de un archivo CSV, aplica la fórmula lineal híbrida,
    filtra según el umbral y exporta los archivos con las recomendaciones finales.
    
    Fórmula: Score = Similarity * (1 - X) + Ollama * X
    """
    raw_scores_path = Path(raw_scores_path)
    output_dir = Path(output_dir)
    
    # Crear el directorio de salida si no existe
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not raw_scores_path.exists():
        logger.error(f"El archivo de puntuaciones en bruto no existe en: {raw_scores_path}")
        return
        
    logger.info(f"Cargando puntuaciones en bruto desde {raw_scores_path}...")
    df = pd.read_csv(raw_scores_path)
    
    # Asegurar tipos de datos correctos para operaciones matemáticas
    df['similarity_score'] = df['similarity_score'].astype(float)
    df['ollama_score'] = df['ollama_score'].astype(float)
    df['rule_id'] = df['rule_id'].astype(str)  # Para concatenar fácilmente con ';'
    
    # Obtener el listado único de consultas originales para preservar la estructura
    unique_queries = df['query'].unique()
    
    # Obtener el nombre base del modelo para nombrar los archivos de salida
    model_name = raw_scores_path.stem.replace("_raw_scores", "")
    
    # Bucle anidado para evaluar cada combinación de hiperparámetros
    for w in weights:
        for t in thresholds:
            logger.info(f"Evaluando combinación -> Peso Ollama (X): {w:.2f} | Umbral: {t:.2f}")
            
            # 1. Aplicar la fórmula lineal ponderada vectorialmente
            df['combined_score'] = (df['similarity_score'] * (1.0 - w)) + (df['ollama_score'] * w)
            
            # 2. Filtrar las reglas que superan o igualan el umbral
            mask_accepted = df['combined_score'] >= t
            filtered_df = df[mask_accepted]
            
            # 3. Agrupar por consulta y concatenar los IDs de las reglas con punto y coma ';'
            grouped = filtered_df.groupby('query')['rule_id'].apply(lambda ids: ';'.join(ids)).reset_index()
            grouped.columns = ['query', 'rule_ids']
            
            # 4. Asegurar la inclusión de consultas que no obtuvieron ninguna recomendación (fijar como 'None')
            final_results = pd.DataFrame({'query': unique_queries})
            final_results = final_results.merge(grouped, on='query', how='left')
            final_results['rule_ids'] = final_results['rule_ids'].fillna('None')
            
            # 5. Generar archivo de salida descriptivo (ej: gemma3_27b-it-q4_K_M_w50_t40.csv)
            weight_pct = int(w * 100)
            thresh_pct = int(t * 100)
            output_file = output_dir / f"{model_name}_w{weight_pct}_t{thresh_pct}.csv"
            
            # Guardar el CSV final
            final_results.to_csv(output_file, index=False, encoding='utf-8')
            logger.info(f"Resultados exportados con éxito a: {output_file}")

if __name__ == "__main__":
    # 1. Especifica la ruta de uno de tus archivos generados en el paso anterior
    RAW_CSV_FILE = "evaluations/raw/gemma3_27b-it-q8_0_raw_scores.csv"
    
    # 2. Carpeta donde deseas almacenar los resultados de la evaluación offline
    OUTPUT_FOLDER = "evaluations/grid_search/"
    
    # 3. Define la lista de Pesos de Ollama (X) que deseas testear
    # 0.0 -> Usa solo Similitud matemática (TF-IDF/BERT)
    # 0.5 -> Equilibrio del 50% entre ambos módulos
    # 1.0 -> Confía ciegamente al 100% en el criterio de Ollama
    PESOS_OLLAMA = [0.3, 0.4, 0.5, 0.6, 0.7, 1.0]
    
    # 4. Define la lista de Umbrales de puntuación (Thresholds) mínimos para filtrar
    UMBRALES = [0.3, 0.4, 0.5, 0.6, 0.7]
    
    # Ejecutar el análisis matemático instantáneo
    evaluate_grid_search(RAW_CSV_FILE, OUTPUT_FOLDER, PESOS_OLLAMA, UMBRALES)
    logger.info("¡Barrido de parámetros finalizado por completo!")