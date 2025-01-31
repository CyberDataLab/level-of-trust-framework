import morph_kgc


path="./prueba.json"
# Definir la ruta de tu archivo de mapeo
mapping_path =  """
                    [DataSource]
                    mappings: nuevo-mapping.rml.ttl
                    file_path: /home/alfonso/Escritorio/TFG/lotaf/level-of-trust-framework/Knowledge-graph-for-LoTAF/Ontology_implementation/prueba.json
                """

# Generar las tripletas RDF
g = morph_kgc.materialize(mapping_path)

# Guardar las tripletas en un archivo RDF
g.serialize(destination="salida.rdf", format="xml")
