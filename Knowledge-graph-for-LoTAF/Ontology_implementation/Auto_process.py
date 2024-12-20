from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from neo4j import GraphDatabase
import os
import morph_kgc

# Define the Neo4j connection details

NEO4J_URI = "bolt://localhost"
USERNAME = "neo4j"
PASSWORD = "PASSWORD"


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


# Connection with Neo4j
driver = GraphDatabase.driver(NEO4J_URI, auth=(USERNAME, PASSWORD))

@app.get("/delete_config")
def delete_config():
    try:
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
        return JSONResponse(content={"message": "Configuration deleted successfully"}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"message": f"An error occurred: {str(e)}"}, status_code=500)
    
@app.get("/remove_graph")
def remove_graph():
    try:
        with driver.session() as session:
            query = """
                        MATCH (r:Resource) DETACH DELETE r
                    """
            session.execute_write(lambda tx: tx.run(query))

        return JSONResponse(content={"message": "Graph removed successfully."}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"message": f"An error occurred: {str(e)}"}, status_code=500)


@app.get("/start_config")        
def start_config():
    try:
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
        return JSONResponse(content={"message": "Neo4j configuration completed successfully."}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"message": f"An error occurred: {str(e)}"}, status_code=500)

@app.get("/load_triplets")
def load_triplets(file_path: str):

    if os.path.exists(file_path):
        file_path = file_path.replace("\\", "/")

        try:
            with driver.session() as session:
                # Import RDF data with neosemantics
                query = f"""
                        CALL n10s.rdf.import.fetch("file:///{file_path}", 'RDF/XML')
                        """
                # Execute command
                session.execute_write(lambda tx: tx.run(query))
            return JSONResponse(content={"message": "RDF triplets loaded successfully."}, status_code=200)
        except Exception as e:
            return JSONResponse(content={"message": f"An error occurred while loading RDF triplets into Neo4j: {str(e)}"}, status_code=500)
    else:
        return JSONResponse(content={"message": "File not found at the specified path."}, status_code=404)

    
    

if __name__ == "__main__":

    
    # This will allow the FastAPI app to be launached as a standalone application
    uvicorn.run("Auto_process:app", host="127.0.0.1", port=8000, reload=True)
    # Local documentation -> http://127.0.0.1:8000/docs

