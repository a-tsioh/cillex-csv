from collections import namedtuple
import SPARQLWrapper
from SPARQLWrapper import SPARQLWrapper, JSON
import urllib2


HEADER_ENTITIES = [["@Entity: #URI", "label"]]

HEADER_EDGES = [["_ObjectProperty: label"]]

HEADER_LITERAL = [["@Litteral: #id", "label", "shape"]]

HEADER_LITERAL_EDGES = [["_DataProperty: label"]]

def get_sparql_endpoint(): return SPARQLWrapper("http://silene.magistry.fr:3030/silene/sparql")  # todo: sparql endpoint as option


def rdf_get_var(x, l): return x[l]['value']


def escape_uri(q):
    if q.startswith("http://"):
        q = q[7:]
        uri = "http://" + urllib2.quote(q.encode("utf-8"))
    else:
        parts = q.split(":", 1)
        if len(parts) > 1:
            pfx = parts[0] + ":"
            q = parts[1]
        uri = pfx + urllib2.quote(q.encode("utf-8"))
    return uri


def rdf_label_of_uri_unsafe(sparql, uri):
    sparql_query = """
        PREFIX sino: <http://silene.magistry.fr/data/nan/sinogram/>
        PREFIX sln: <http://silene.magistry.fr/ns#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX decomp: <http://www.w3.org/ns/lemon/decomp#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>

        SELECT ?label
        WHERE {
            <%s> rdfs:label ?label .

        }
        """ % (uri,)
    sparql.setQuery(sparql_query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    data = results['results']['bindings']
    entities = []
    properties = []
    label = uri
    for row in data:
        label = rdf_get_var(row, "label")
    return label

def get_data_properties(sparql, q):
    sparql_query = """
    PREFIX sino: <http://silene.magistry.fr/data/nan/sinogram/>
    PREFIX sln: <http://silene.magistry.fr/ns#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX decomp: <http://www.w3.org/ns/lemon/decomp#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>

    SELECT ?v ?o
    WHERE {
        <%s> ?v ?o . 
        ?v a owl:DatatypeProperty .
    }
    """ % (q,)
    sparql.setQuery(sparql_query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    data = results['results']['bindings']
    literals = []
    edges = []
    for row in data:
        (v, o) = (rdf_get_var(row, "v"), rdf_get_var(row, "o"))
        id = q + ":" + o
        literals.append([id, o, "square"])
        edges.append(["%s -- %s" % (q, id), v.split("/")[-1]])
        # properties.append([q, o_uri, v])
    return literals, edges


def get_neighbors_entities(sparql, q):
    sparql_query = """
    PREFIX sino: <http://silene.magistry.fr/data/nan/sinogram/>
    PREFIX sln: <http://silene.magistry.fr/ns#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX decomp: <http://www.w3.org/ns/lemon/decomp#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>

    SELECT ?v ?o ?olabel
    WHERE {
        { <%s> ?v ?o . }  
        ?v a owl:ObjectProperty .
        ?o rdfs:label ?olabel .

    }
    """ % (q,)
    sparql.setQuery(sparql_query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    data = results['results']['bindings']
    entities = []
    properties = []
    for row in data:
        (v, o_uri, o_label) = (rdf_get_var(row, "v"), rdf_get_var(row, "o"), rdf_get_var(row, "olabel"))
        entities.append([o_uri, o_label])
        properties.append(["%s -- %s" % (q, o_uri), v.split("/")[-1]])
        # properties.append([q, o_uri, v])
    return entities, properties


def simple_query(q, escape=True):
    print(q)
    sparql = get_sparql_endpoint()
    entities = []
    literals = []
    data_properties = []
    object_properties = []
    if escape:
        uri = escape_uri(q)
    else:
        uri = q
    entities.append([uri, rdf_label_of_uri_unsafe(sparql, uri)])

    (vtx,edges) = get_neighbors_entities(sparql, uri)
    entities.extend(vtx)
    object_properties.extend(edges)

    (vtx, edges) = get_data_properties(sparql, uri)
    literals.extend(vtx)
    data_properties.extend(edges)

    graph_data = HEADER_ENTITIES + entities + HEADER_EDGES + object_properties + HEADER_LITERAL + literals + HEADER_LITERAL_EDGES + data_properties
    print("\n".join([" , ".join(l) for l in graph_data]))
    return graph_data
