import morph_kgc

# Definir la ruta de tu archivo de mapeo
mapping_path =  """
                    [DataSource]
                    mappings: nuevo-mapping.rml.ttl
                """

# Generar las tripletas RDF
g = morph_kgc.materialize(mapping_path)

# Guardar las tripletas en un archivo RDF
g.serialize(destination="output.rdf", format="xml")
