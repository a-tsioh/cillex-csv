#!/usr/bin/env python
#-*- coding:utf-8 -*-

from flask import request, jsonify

import igraph
import datetime
import requests

from collections import Counter

from reliure.types import GenericType, Text, Numeric, Boolean
from reliure.web import ReliureAPI, EngineView, ComponentView, RemoteApi
from reliure.pipeline import Optionable, Composable
from reliure.engine import Engine

from cello.graphs import pedigree
from cello.graphs import export_graph, IN, OUT, ALL
from cello.graphs.prox import ProxSubgraph, pure_prox, sortcut
from cello.graphs.extraction import ProxMarkovExtraction

from cello.layout import export_layout
from cello.clustering import export_clustering

from pdgapi.explor import ComplexQuery, AdditiveNodes, NodeExpandQuery, prepare_graph, export_graph, layout_api, clustering_api

from botapi import BotaIgraph
from botapad import Botapad

import istex2csv as istex
import rdf2csv as rdf


@Composable
def query_rdf(gid, q, graph=None, escape=True, **kwargs):

    data = rdf.simple_query(q, escape)

    bot = BotaIgraph(directed=True)
    botapad = Botapad(bot, gid, "", delete=False, verbose=True, debug=False)

    botapad.parse_csvrows(data, separator='auto', debug=False)
    g = bot.get_igraph(weight_prop="weight")
    g = prepare_graph(g)

    g['meta']['date'] = datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")
    g['meta']['owner'] = None
    g['query'] = {'q': q}
    return g


@Composable
def db_graph(graphdb, query, **kwargs):
    gid = query['graph']
    try : 
        graph = graphdb.get_graph(gid)
    except Exception as e:
        graph = empty_graph(gid, **kwargs)
        graphdb.graphs[gid] = graph

    return query, graph


def vid(gid, v):
    if v['nodetype'] == ("_%s_article" % gid):
        e =  v['properties']['id']
    else :
        e =  v['nodetype'] + v['properties']['label']
    return e

@Composable
def index(gid, graph, **kwargs):
    idx = { vid(gid, v): v for v in graph.vs }
    return idx

def types_stats( items , opt={}):
    counter = Counter(items)
    return dict(counter)  
    print counter

@Composable
def graph_stats(graph, **kwargs):
    graph['meta']['stats'] = {}

    stats = types_stats(graph.vs['nodetype'])
    print stats
    for e in graph['nodetypes']:
        e['count'] = stats.get(e['uuid'], 0)
    graph['meta']['stats']['nodetypes'] = stats
    
    stats = types_stats(graph.es['edgetype'])
    for e in graph['edgetypes']:
        e['count'] = stats.get(e['uuid'], 0)
    graph['meta']['stats']['edgetypes'] = stats
    return graph

@Composable
def merge(gid, graph, g, **kwargs):
    """ merge g into graph, returns graph"""
    idx = index(gid, graph)
    
    nodetypes = [ e['name'] for e in graph['nodetypes'] ]
    for k in g['nodetypes']:
        if k['name'] not in nodetypes:
            graph['nodetypes'].append(k)

    nodetypes = { e['uuid']: e  for e in graph['nodetypes'] }
    for v in g.vs:
        _vid = vid(gid,v)
        if _vid not in idx:
                uuid = "%s" % graph.vcount()
                attrs = v.attributes()
                attrs['uuid'] = uuid

                nodetype = nodetypes[attrs['nodetype']]
                properties = nodetype['properties']
                for k in properties:
                    if k not in attrs['properties']:
                        attrs['properties'][k] = properties[k]['default']
                
                graph.add_vertex( **attrs )
                idx[ _vid ] = graph.vs[graph.vcount()-1]
                
                            
    edgetypes = [ e['name'] for e in graph['edgetypes'] ]
    for k in g['edgetypes']:
        if k['name'] not in edgetypes:
            graph['edgetypes'].append(k)

    edgetypes = { e['uuid']: e  for e in graph['edgetypes'] }
    for e in g.es:
        v1, v2 = (vid(gid, g.vs[e.source] ), vid(gid, g.vs[e.target]) )
        #if v1 in idx 
        v1, v2 = ( idx[v1], idx[v2] )
        eid = graph.get_eid( v1, v2 , directed=True, error=False )
        if eid == -1:
            e['uuid'] = graph.ecount()
            attrs = e.attributes()
            edgetype = edgetypes[attrs['edgetype']]
            properties = edgetype['properties']
            for k in properties:
                if k not in attrs['properties']:
                    attrs['properties'][k] = properties[k]['default']
            
            graph.add_edge( v1, v2, **attrs )

    graph['queries'].append(g['query'])
    graph['meta'] = {
            'node_count': graph.vcount(),
            'edge_count': graph.ecount(),
            'star_count': len( graph['starred'] ),
            'owner': None,
            'date': None,
            #'date' : datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")
        }
    graph['meta']['pedigree'] = pedigree.compute(graph)
    graph = graph_stats(graph)    
    return graph
    
@Composable
def empty_graph(gid, headers=None, **kwargs):

    headers = headers if headers else istex.get_schema()
    
    bot = BotaIgraph(directed=True)
    botapad = Botapad(bot , gid, "", delete=False, verbose=True, debug=False)
    botapad.parse_csvrows( headers, separator='auto', debug=False)

    graph = bot.get_igraph(weight_prop="weight")
    graph = prepare_graph(graph)
    graph['starred'] = []
    graph['queries'] = []
    graph['meta'] = {  
            'owner': None,
            'date': None,
            #'date' : datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")
            'node_count': graph.vcount(),
            'edge_count': graph.ecount(),
            'star_count': len( graph['starred'] ),
            'stats' : {}
        }
    #graph['meta']['pedigree'] = pedigree.compute(graph)

    return graph

  
@Composable
def query_istex(gid, q, field, count=10, graph=None,**kwargs):
    url = istex.to_istex_url(q, field, count)
    g = istex.request_api_to_graph(gid, url, graph)
    g = prepare_graph(g)
    
    g['meta']['date'] = datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")
    g['meta']['owner'] = None
    g['query'] = { 'q': q, 'field':field , 'url':url}
    
    return g



def _weights(weightings):
    def _w( graph, vertex):

        r = [(vertex, 1)] # loop
        
        for i in graph.incident(vertex, mode=ALL):
            e = graph.es[i]
            v = e.source if e.target == vertex else e.target

            w = (v, 1) # default

            if weightings:
                if "0" in weightings : 
                    w = (v, 0)
                if "1" in weightings : 
                    w = (v, 1)
            
                if "weight" in weightings:
                    w = (v, e['weight'])
                    
                if "auteurs" in weightings:
                    if "_auteurs" in e['edgetype'].lower() : 
                        w = (v, 5) 
                        
                if "refBibAuteurs" in weightings:
                    if "_refBibAuteurs" in e['edgetype'] :
                        w = (v, 5)
                        
                if "keywords" in weightings :
                    if "keywords" in e['edgetype'] :
                        w =(v, 5)
                    
                if "categories" in weightings :
                    if  "categories" in e['edgetype']:
                        w = (v, 5)

            r.append( w )
                
        return r
    return _w

@Composable
def extract_articles(gid, graph, pz, weighting=None, length=3,  **kwargs):
    """
    : weight  :  scenario in ( '' , '' )
    """
    if weighting is None:
        weighting = ["1"]
        
    wneighbors = _weights(weighting)
    vs = pure_prox(graph, pz, length, wneighbors)
    return  vs

@Composable
def graph_articles(gid, graph, all_articles=True, cut=200, uuids=[], **kwargs):

    pz = [ (v.index,1.) for v in graph.vs if v['nodetype'] == ("_%s_article" % gid) ]

    if uuids and len(uuids):
        vids = [ v.index for v in graph.vs.select( uuid_in=uuids ) ]
        vs = extract_articles(gid, graph, dict(pz), **kwargs)
        vs = sortcut(vs,cut + len(vids) )
        vs = [ (v,s) for v,s in vs if v not in vids ][:cut]
        vs = vs + [ (v,1.) for v in vids ]
    else : 
        vs = extract_articles(gid, graph, dict(pz), **kwargs)
        vs = sortcut(vs,cut)

    if all_articles :
        vs = pz + vs
        
    return graph.subgraph( dict(vs).keys() )

    
def search_engine(graphdb):
    # setup
    engine = Engine("search")
    engine.search.setup(in_name="request", out_name="graph")

    ## Search
    def Search(query, **kwargs):
        query, graph = db_graph(graphdb, query)
        gid = query['graph']
        
        q = kwargs.pop("URI")
        # field = kwargs.pop("field", None)
        
        #g = query_istex(gid, q, field)
        g = query_rdf(gid, q)
        graph = merge(gid, graph, g)

        nodes = query['nodes']
        #g = graph_articles(gid, graph, weighting=["1"], all_articles=True, cut=100, uuids=nodes, **kwargs )
        return graph
        
    search = Optionable("RDFSearch")
    search._func = Search
    search.add_option("URI", Text(default=u"sino:好"))
    # search.add_option("field", Text(choices=[ u"*", u"istex", u"auteurs", u"refBibAuteurs", u"keywords" ], default=u"*"))
    # search.add_option("results_count", Numeric( vtype=int, min=1, default=10, help="Istex results count"))
    
    engine.search.set( search )
    return engine
 

def graph_engine(graphdb):
    # setup
    engine = Engine("graph")
    engine.graph.setup(in_name="request", out_name="graph")

    def _global(query, reset=False, all_articles=False, cut=100,  **kwargs):

        gid = query['graph']
        query, graph = db_graph(graphdb, query)
        nodes = [] if reset else query['nodes']
        g = graph_articles(gid, graph, all_articles=all_articles, cut=cut, uuids=nodes, **kwargs )
        return g
        
    comp = Optionable("Graph")
    comp._func = _global
    comp.add_option("reset", Boolean( default=False , help="reset or add"))
    comp.add_option("all_articles", Boolean( default=False , help="includes all articles"))
    comp.add_option("weighting", Text(choices=[  u"0", u"1", u"weight" , u"auteurs", u"refBibAuteurs", u"keywords", u"categories" ], multi=True, default=u"1", help="ponderation"))
    comp.add_option("length", Numeric( vtype=int, min=1, default=3))
    comp.add_option("cut", Numeric( vtype=int, min=2, default=100))

    def _reset_global(query, **kwargs):
        gid = query['graph']
        graph = empty_graph(gid, **kwargs)
        graphdb.graphs[gid] = graph
        g = graph_articles(gid, graph, all_articles=True, uuids=[], **kwargs )
        return g

    reset = Optionable('ResetGraph')
    reset._func = _reset_global
    reset.add_option("reset", Boolean( default=True , help="") , hidden=True)
    
    engine.graph.set( comp, reset )
    return engine

 
def import_calc_engine(graphdb):
    def _import_calc(query, calc_id=None, **kwargs):
        query, graph = db_graph(graphdb, query)
        if calc_id == None:
            return None
        url = "http://calc.padagraph.io/cillex-%s" % calc_id
        graph = istex.pad_to_graph(calc_id, url)
        graph['meta']['pedigree'] = pedigree.compute(graph)
        graph['properties']['description'] = url
        graphdb.graphs[calc_id] = graph
        return graph_articles(calc_id, graph, cut=100)
        
    comp = Optionable("import_calc")
    comp._func = _import_calc
    comp.add_option("calc_id", Text(default=None, help="identifiant du calc,le calc sera importé depuis l'adresse http://calc.padagraph.io/cillex-{calc-id}"))
    
    engine = Engine("import_calc")
    engine.import_calc.setup(in_name="request", out_name="graph")
    engine.import_calc.set( comp )

    return engine
 
def export_calc_engine(graphdb):
    def _export_calc(query, calc_id=None, **kwargs):

        if calc_id == None:
            return { 'message' : "No calc_id ",
                 'gid' : calc_id ,
                 'url': ""
                }
                
        query, graph = db_graph(graphdb, query)
        url = "http://calc.padagraph.io/_/cillex-%s" % calc_id
        print "_export_calc", query, calc_id, url

        headers, rows = istex.graph_to_calc(graph)
        print( "* PUT %s %s " % (url, len(rows)) ) 
        
        r = requests.put(url, data=istex.to_csv(headers, rows))
        url = "http://calc.padagraph.io/cillex-%s" % calc_id

        return { 'message' : "Calc exported ",
                 'gid' : calc_id ,
                 'url': url
                }
        
    export = Optionable("export_calc")
    export._func = _export_calc
    export.add_option("calc_id", Text(default=None, help="identifiant du calc, le calc sera sauvegardé vers l’adresse http://calc.padagraph.io/cillex-{calc-id}"))
    
    engine = Engine("export")
    engine.export.setup(in_name="request", out_name="url")
    engine.export.set( export )

    return engine



@Composable
def extract(graph, pz, cut=50, weighting=None, length=3, **kwargs):
    wneighbors = _weights(weighting)
    vs = pure_prox(graph, pz, length, wneighbors)
    vs = sortcut(vs,cut)
    return vs
    
def expand_prox_engine(graphdb):
    """
    prox with weights and filters on UNodes and UEdges types
    input:  {
                nodes : [ uuid, .. ],  //more complex p0 distribution
                weights: [float, ..], //list of weight
            }
    output: {
                graph : gid,
                scores : [ (uuid_node, score ), .. ]
            }
    """
    engine = Engine("scores")
    engine.scores.setup(in_name="request", out_name="scores")

    @Composable
    def Expand(query, **kwargs):
        
        query, graph = db_graph(graphdb, query)
        gid = query.get("graph")
        
        field = "*"
        nodes = query['nodes']
        vs = graph.vs.select( uuid_in=nodes )
        
        if len(vs) == 0 :
            raise ValueError('No such node %s' % nodes)

        v = vs[0]
        q = v['properties']['URI']
        if ( v['nodetype'] == "Entity" ):
            q = v['properties']['URI']
        elif ( v['nodetype'] == "Literal" ):
            q = v['properties']['id']
        print(q)
        g = query_rdf(gid, q, escape=False)
        graph = merge(gid, graph, g)

        pz = [ v.index ]
        vs = extract(graph, pz, **kwargs)
        print(vs)
        vs = [ (graph.vs[i]['uuid'], v) for i, v in vs]
        # articles = [ (v['uuid'], 1.) for v in graph.vs if v['nodetype'] == ("_%s_article" % gid) ]
        return dict( vs)

    scores = Optionable("scores")
    scores._func = Expand
    scores.name = "expand"
    engine.scores.set(scores)

    return engine


def explore_api(engines,graphdb ):
    #explor_api = explor.explore_api("xplor", graphdb, engines)
    api = ReliureAPI("xplor",expose_route=False)

    # import pad
    view = EngineView(import_calc_engine(graphdb))
    view.set_input_type(AdditiveNodes())
    view.add_output("graph", export_graph, id_attribute='uuid'  )
    api.register_view(view, url_prefix="import")    

    # istex search
    view = EngineView(search_engine(graphdb))
    view.set_input_type(ComplexQuery())
    view.add_output("request", ComplexQuery())
    view.add_output("graph", export_graph, id_attribute='uuid')

    api.register_view(view, url_prefix="search")

    # graph exploration, reset global
    view = EngineView(graph_engine(graphdb))
    view.set_input_type(ComplexQuery())
    view.add_output("request", ComplexQuery())
    view.add_output("graph", export_graph, id_attribute='uuid')

    api.register_view(view, url_prefix="graph")

    # prox expand returns [(node,score), ...]
    view = EngineView(expand_prox_engine(graphdb))
    view.set_input_type(NodeExpandQuery())
    view.add_output("scores", lambda x: x)

    api.register_view(view, url_prefix="expand_px")

    # additive search
    view = EngineView(engines.additive_nodes_engine(graphdb))
    view.set_input_type(AdditiveNodes())
    view.add_output("graph", export_graph, id_attribute='uuid'  )

    api.register_view(view, url_prefix="additive_nodes")    

    # export pad
    view = EngineView(export_calc_engine(graphdb))
    view.set_input_type(AdditiveNodes())
    view.add_output("url", lambda e: e )
    api.register_view(view, url_prefix="export")    

    return api


class Clusters(GenericType):
    def parse(self, data):
        gid = data.get('graph', None)
        clusters = data.get('clusters', None)

        if gid is None :
            raise ValueError('graph should not be null')
        if clusters is None :
            raise ValueError('clusters should not be null')

        return data
 
def clusters_labels_engine(graphdb):
    def _labels(query, weighting=None, count=2, **kwargs):
        query, graph = db_graph(graphdb, query)
        gid = query['graph']
        clusters = []
        for clust in query['clusters']:
            labels = []
            pz = graph.vs.select(uuid_in=clust)
            pz = [ v.index for v in pz if  v['nodetype'] == ("_%s_article" % gid ) ]
            if len(pz):
                vs = extract(graph, pz, cut=300, weighting=weighting, length=3)
                labels = [ { 'uuid' : graph.vs[i]['uuid'],
                             'label' : graph.vs[i]['properties']['label'],
                             'score' :  v }  for i,v in vs if graph.vs[i]['nodetype'] != ("_%s_article" % gid )][:count]
            clusters.append(labels)
        return clusters
        
    comp = Optionable("labels")
    comp._func = _labels
    comp.add_option("weighting", Text(choices=[  u"0", u"1", u"weight" , u"auteurs", u"refBibAuteurs", u"keywords", u"categories" ], multi=True, default=u"1", help="ponderation"))
    comp.add_option("count", Numeric( vtype=int, min=1, default=2))
    
    engine = Engine("labels")
    engine.labels.setup(in_name="request", out_name="labels")
    engine.labels.set( comp )

    return engine

# Clusters

def clustering_api(graphdb, engines, api=None, optionables=None, prefix="clustering"):
    
    def clustering_engine(optionables):
        """ Return a default engine over a lexical graph
        """
        # setup
        engine = Engine("gbuilder", "clustering")
        engine.gbuilder.setup(in_name="request", out_name="graph", hidden=True)
        engine.clustering.setup(in_name="graph", out_name="clusters")

        engine.gbuilder.set(engines.edge_subgraph) 
        engine.clustering.set(*optionables)

        return engine
        
    if api is None:
        api = ReliureAPI(name,expose_route = False)
        
    ## Clustering
    from cello.graphs.transform import EdgeAttr
    from cello.clustering.common import Infomap, Walktrap
    # weighted
    walktrap = Walktrap(weighted=True)
    walktrap.name = "Walktrap"
    infomap = Infomap(weighted=True) 
    infomap.name = "Infomap"

    DEFAULTS = [walktrap, infomap]

    if optionables == None : optionables = DEFAULTS

    from pdgapi.explor  import EdgeList
    view = EngineView(clustering_engine(optionables))
    view.set_input_type(EdgeList())
    view.add_output("clusters", export_clustering,  vertex_id_attr='uuid')
    api.register_view(view, url_prefix=prefix)

    # cluster labels
    view = EngineView(clusters_labels_engine(graphdb))
    view.set_input_type(Clusters())
    view.add_output("labels", lambda e: e )
    api.register_view(view, url_prefix="labels")
  

    return api