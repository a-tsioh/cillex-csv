#!/usr/bin/env python
#-*- coding:utf-8 -*-

from flask import request, jsonify

import igraph
import datetime
import requests

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
    
@Composable
def merge(gid, graph, g, **kwargs):
    """ merge g into graph, returns graph"""
    idx = index(gid, graph)
    
    nodetypes = [ e['name'] for e in graph['nodetypes'] ]
    for k in g['nodetypes']:
        if k['name'] not in nodetypes:
            graph['nodetypes'].append(k)
                            
    edgetypes = [ e['name'] for e in graph['edgetypes'] ]
    for k in g['edgetypes']:
        if k['name'] not in edgetypes:
            graph['edgetypes'].append(k)

    for v in g.vs:
        _vid = vid(gid,v)
        if _vid not in idx:
                uuid = "%s" % graph.vcount()
                attrs = v.attributes()
                attrs['uuid'] = uuid
                graph.add_vertex( **attrs )
                idx[ _vid ] = graph.vs[graph.vcount()-1]
                
    for e in g.es:
        v1, v2 = (vid(gid, g.vs[e.source] ), vid(gid, g.vs[e.target]) )
        #if v1 in idx 
        v1, v2 = ( idx[v1], idx[v2] )
        eid = graph.get_eid( v1, v2 , directed=True, error=False )
        if eid == -1:
            e['uuid'] = graph.ecount()
            graph.add_edge( v1, v2, **e.attributes() )

    graph['meta'] = {
            'node_count': graph.vcount(),
            'edge_count': graph.ecount(),
            'owner': "-",
            'star_count': len( graph['starred'] ),
            'date' : datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")
        }
    graph['meta']['pedigree'] = pedigree.compute(graph)
        
    return graph
    
@Composable
def empty_graph(gid, **kwargs):

    headers = istex.get_schema()
    
    bot = BotaIgraph(directed=True)
    botapad = Botapad(bot , gid, "", delete=False, verbose=True, debug=False)
    botapad.parse_csvrows( headers, separator='auto', debug=False)

    graph = bot.get_igraph(weight_prop="weight")
    graph = prepare_graph(graph)
    graph['starred'] = []
    graph['meta'] = {
            'owner': None,
            'node_count': graph.vcount(),
            'edge_count': graph.ecount(),
            'star_count': len( graph['starred'] ),
            'date' : datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")
        }
    #graph['meta']['pedigree'] = pedigree.compute(graph)

    return graph

  
@Composable
def query_istex(gid, q, field, count=10, **kwargs):
    url = istex.to_istex_url(q, field, count)
    graph = istex.request_api_to_graph(gid, url)
    graph = prepare_graph(graph)
    
    graph['meta']['date'] = datetime.datetime.now().strftime("%Y-%m-%d %Hh%M")
    graph['meta']['owner'] = None
    graph['meta']['query'] = q
    
    #graph['meta']['pedigree'] = pedigree.compute(graph)
    return graph
    

def _weights(weighting):
    def _w( graph, vertex):
        r = [(vertex, 1)] # loop
        for i in graph.incident(vertex, mode=ALL):
            e = graph.es[i]
            v = e.source if e.target == vertex else e.target

            if weighting == "weight":
                r.append( (v, e['weight']) )
                
            elif weighting == "auteurs":
                if "auteurs" in e['edgetype'].lower() : # auteurs + refBibAuteurs
                    r.append( (v, 5) )
                elif "keywords" in e['edgetype'] or "categories" in e['edgetype']:
                    r.append( (v, 0.1) )
                else : r.append( (v, 1) )
                    
            elif weighting == "keywords" :
                if "auteurs" in e['edgetype'].lower() : # auteurs + refBibAuteurs
                    r.append( (v, 0.1) )
                elif "keywords" in e['edgetype'] or "categories" in e['edgetype']:
                    r.append( (v, 5) )
                else : r.append( (v, 1) )
                
            elif weighting in ("1", None) : 
                r.append( (v, 1) )
        
        return r
    return _w

@Composable
def extract_articles(gid, graph, cut=100, weighting=None, length=3):
    """
    : weight  :  scenario in ( '' , '' )
    """
    pz = [ v.index for v in graph.vs if v['nodetype'] == ("_%s_article" % gid) ]
    wneighbors = _weights(weighting)
    
    vs = pure_prox(graph, pz, length, wneighbors)
    vs = dict(sortcut(vs,cut))
    return vs.keys()
    
def graph_articles(gid, graph, **kwargs):
    vs = extract_articles(gid, graph, **kwargs)
    return graph.subgraph( vs )
    
def search_engine(graphdb):
    """ Prox engine """
    # setup
    engine = Engine("graph")
    engine.graph.setup(in_name="request", out_name="graph")

    ## Search
    def Search(query, results_count=10, **kwargs):
        query, graph = db_graph(graphdb, query)
        gid = query['graph']
        
        q = kwargs.pop("q", "*")
        field = kwargs.pop("field", None)
        
        g = query_istex(gid, q, field, results_count)
        graph = merge(gid, graph, g)
        #graphdb.graphs[gid] = graph

        g = graph_articles(gid, graph,  **kwargs)
        return g
        
    search = Optionable("IstexSearch")
    search._func = Search
    search.add_option("q", Text(default=u"clle erss"))
    search.add_option("field", Text(choices=[ u"*", u"istex", u"auteurs", u"refBibAuteurs" ], default=u"*"))
    search.add_option("results_count", Numeric( vtype=int, min=1, default=10, help="Istex results count"))
    
    from cello.graphs.transform import VtxAttr
    #search |= VtxAttr(color=[(45, 200, 34), ])
    #search |= VtxAttr(type=1)

    def _global(query, **kwargs):
        query, graph = db_graph(graphdb, query)
        g = graph_articles(query['graph'], graph, **kwargs)
        
        return g
        
    global_graph = Optionable("Global")
    global_graph._func = _global
    global_graph.add_option("weighting", Text(choices=[ u"1" ,u"weight" , u"keywords", u"auteurs"], default=u"1", help="ponderation"))
    global_graph.add_option("length", Numeric( vtype=int, min=1, default=3))
    global_graph.add_option("cut", Numeric( vtype=int, min=2, default=100))
    
    engine.graph.set( search, global_graph )
    return engine
 
def import_calc_engine(graphdb):
    def _import_calc(query, calc_id=None, **kwargs):
        query, graph = db_graph(graphdb, query)
        if calc_id == None:
            return None
        url = "http://calc.padagraph.io/cillex-%s" % calc_id
        graph = istex.pad_to_graph(calc_id, url)
        graphdb.graphs[calc_id] = graph
        return graph_articles(calc_id, graph, cut=100)
        
    comp = Optionable("import_calc")
    comp._func = _import_calc
    comp.add_option("calc_id", Text(default=None, help="url to import calc"))
    
    engine = Engine("import_calc")
    engine.import_calc.setup(in_name="request", out_name="graph")
    engine.import_calc.set( comp )

    return engine
 
def export_calc_engine(graphdb):
    def _export_calc(query, calc_url=None, **kwargs):
        query, graph = db_graph(graphdb, query)
        if calc_url == None:
            return None
        url = "http://calc.padagraph.io/_/cillex-%s" % calc_url
        print "_export_calc", query, calc_url, url

        headers, rows = istex.graph_to_calc(graph)
        print headers
        print rows
        
        print( "* PUT %s %s " % (url, len(rows)) ) 
        r = requests.put(url, data=istex.to_csv(headers, rows))
        return url
        
    export = Optionable("export_calc")
    export._func = _export_calc
    export.add_option("calc_url", Text(default=None, help="url to export calc"))
    
    engine = Engine("export")
    engine.export.setup(in_name="request", out_name="url")
    engine.export.set( export )

    return engine



@Composable
def extract_expand(graph, pz, cut=50, weighting=None, length=3, **kwargs):
    wneighbors = _weights(weighting)
    vs = pure_prox(graph, pz, length, wneighbors)
    vs = dict(sortcut(vs,cut)).keys()
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
        v = graph.vs.select( uuid_in=query['nodes'] )[0]
        if ( v['nodetype'] == ("_%s_auteurs" % gid) ):
            field = "auteurs"
            q = v['properties']['label']
        elif ( v['nodetype'] == ("_%s_refBibAuteurs" % gid) ):
            field = "refBibAuteurs"
            q = v['properties']['label']
        else: 
            q = v['properties']['label']

        g = query_istex(gid, q, field)
        graph = merge(gid, graph, g)

        pz = [ v.index ]
        vs = extract_expand(graph, pz, **kwargs)
        
        return vs

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

    # prox search returns graph only
    view = EngineView(search_engine(graphdb))
    view.set_input_type(ComplexQuery())
    view.add_output("request", ComplexQuery())
    view.add_output("graph", export_graph, id_attribute='uuid')

    api.register_view(view, url_prefix="search")

    # prox expand returns [(node,score), ...]
    view = EngineView(expand_prox_engine(graphdb))
    view.set_input_type(NodeExpandQuery())
    view.add_output("scores", lambda x:x)

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

    #layout
    api = layout_api(engines, api)
    #clustering
    api = clustering_api(engines, api)

    return api