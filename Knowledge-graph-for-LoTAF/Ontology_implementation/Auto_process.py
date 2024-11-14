from fastapi import FastAPI
import uvicorn
from neo4j import GraphDatabase
import os
import morph_kgc


# API

app = FastAPI(
    title="Level of Trust Assessment Auto Process Database",
    description="This API describes a process automation",
    version="1.0.0",
    contact={
        "name": "Alfonso Serrano Gil",
        "url": "https://cyberdatalab.um.es/alfonso-serrano-gil/",
        "email": "alfonso.s.g@um.es",
    },
)


MAPPING_FILE = "C:\\Users\\Usuario\\Desktop\\Trabajo\\Pruebas_Ontologia\\lotaf-mapping.rml.ttl"
OUTPUT_MAPPED_FILE = "C:\\Users\\Usuario\\Desktop\\Trabajo\\Pruebas_Ontologia\\output.rdf"

@app.get("/map_data")
def map_data(mapping_file_path: str, output_path: str):

    # Definir la ruta de tu archivo de mapeo
    mapping_path =  f"""
                        [DataSource]
                        mappings: {mapping_file_path}
                    """

    # Generar las tripletas RDF
    g = morph_kgc.materialize(mapping_path)

    # Guardar las tripletas en un archivo RDF
    g.serialize(destination=output_path, format="xml")

    return output_path


# Define the Neo4j connection details

NEO4J_URI = "bolt://localhost"
USERNAME = "neo4j"
PASSWORD = "PASSWORD"

# Ontology file route
# RDF_FILE_PATH = "C:\\Users\\Usuario\\Desktop\\Trabajo\Pruebas_Ontologia\\output.rdf"

# RDF_FILE_PATH = RDF_FILE_PATH.replace("\\", "/")

# Connection with Neo4j
driver = GraphDatabase.driver(NEO4J_URI, auth=(USERNAME, PASSWORD))

@app.get("/delete_config")
def delete_config():
    with driver.session() as session:
        query = """
                    DROP CONSTRAINT n10s_unique_uri IF EXISTS
                """
        session.execute_write(lambda tx: tx.run(query))
    
    with driver.session() as session:
        query = """
                    MATCH (config:_GraphConfig) DETACH DELETE config
                """
        session.execute_write(lambda tx: tx.run(query))

    with driver.session() as session:
        query = """
                    MATCH (n:_NsPrefDef) DETACH DELETE n
                """
        session.execute_write(lambda tx: tx.run(query))

@app.get("/remove_graph")    
def remove_graph():
    with driver.session() as session:
        query = """
                    MATCH (n) DETACH DELETE n
                """
        session.execute_write(lambda tx: tx.run(query))

@app.get("/start_config")        
def start_config():
    with driver.session() as session:
        # Create a unique constraint on URI
        query = """
                CREATE CONSTRAINT n10s_unique_uri FOR (r:Resource) REQUIRE r.uri IS UNIQUE
                """
        session.execute_write(lambda tx: tx.run(query))
    
    with driver.session() as session:
        # Initialize Neosemantics configuration
        query_1 = """
        CALL n10s.graphconfig.init({handleVocabUris: "SHORTEN", handleMultival: "OVERWRITE", handleRDFTypes:"LABELS_AND_NODES"})
        """
        session.execute_write(lambda tx: tx.run(query_1))

    #with driver.session() as session:
        # Add namespace prefix
    #    query_2 = """
    #   CALL n10s.nsprefixes.add('lotaf', 'http://www.owl-ontologies.com/lotaf#')
    #   """
    #   session.execute_write(lambda tx: tx.run(query_2))
    print("Neo4j configuration completed.")

@app.get("/load_triplets")
def load_triplets(file_path: str):

    if os.path.exists(file_path):
        file_path = file_path.replace("\\", "/")


        with driver.session() as session:
            # Import RDF data with neosemantics
            query = f"""
                    CALL n10s.rdf.import.fetch("file:///{file_path}", 'RDF/XML')
                    """
            # Execute command
            session.execute_write(lambda tx: tx.run(query))
            print("Carga de tripletas RDF completada.")
    else:
        print("No existe el fichero")

switch_commands = {
    1: remove_graph,
    2: delete_config,
    3: start_config,
    4: load_triplets,
    5: map_data
}

def read_entry():
    print(f"""(1) Remove previous graph. 
(2) Delete previous config. 
(3) Start config.
(4) Load triplets. 
(5) Map data. \n""")
    
    selection = int(input("Select an option: "))
    switch_commands.get(selection, lambda: print("Error!"))()
    
    

if __name__ == "__main__":

    """
    RDF_FILE_PATH = map_data(MAPPING_FILE, OUTPUT_MAPPED_FILE)
    RDF_FILE_PATH = RDF_FILE_PATH.replace("\\", "/")

    if os.path.exists(RDF_FILE_PATH.replace("/", "\\")):

        remove_graph()
        delete_config()
        start_config()
        load_triplets(RDF_FILE_PATH)
    else:
        print(f"Archivo RDF no encontrado en la ruta especificada: {RDF_FILE_PATH}")
    """
    """
    running = True
    while(running):
        try:
            read_entry()
        except KeyboardInterrupt:
            print("Ended!")
            running = False
    """
    # This will allow the FastAPI app to be launached as a standalone application
    uvicorn.run("Auto_process:app", host="127.0.0.1", port=8000, reload=True)
    # Local documentation -> http://127.0.0.1:8000/docs

