import morph_kgc

# Definir la ruta de tu archivo de mapeo
mapping_path =  """
                    [DataSource]
                    mappings: C:\\Users\\Usuario\\Desktop\\Trabajo\\Pruebas_Ontologia\\lotaf-mapping.rml.ttl
                """

# Generar las tripletas RDF
g = morph_kgc.materialize(mapping_path)

# Guardar las tripletas en un archivo RDF
g.serialize(destination="C:\\Users\\Usuario\\Desktop\\Trabajo\\Pruebas_Ontologia\\output.rdf", format="xml")
