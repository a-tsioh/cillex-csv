#-*- coding:utf-8 -*-

import unicodecsv as csv
import json
import requests
import urllib
import collections
from StringIO import StringIO

from botapi import BotaIgraph
from botapad import Botapad

# parse response attributes
_key = lambda e,k : e.get(k)

def _fulltext(article, k) :
    i = article.get("id")
    url = "https://api.istex.fr/document/%s/fulltext/pdf?sid=istex-api-demo" % i
    return url
    
def _document(article, k) :
    i = article.get("id")
    url = "https://api.istex.fr/document/%s" % i
    return url
    
_label = lambda e,k : e.get('title')
_abstract = lambda e,k : e.get('abstract')

def _keywords(e,k):
    kw = e['keywords']['teeft'] if 'keywords' in e else []
    kw = [ v for v in kw if len(v)> 2 ]
    return ";".join(kw) 

def _list(e, k) :
    return  ";".join(e.get(k, []))

def _auteur(name):
    """ clean auteur name"""
    name = name.lower().strip()
    name = [  v[0].upper() + ("." if len(v) == 1 else v[1:])  for v in name.split() ]
    return " ".join(name)

def _author_names( e, k ):
    auteurs =   [ _auteur(v['name']) for v in  e['author'] ]
    auteurs = [ v for v in auteurs if len(v)> 2 ]
    return clean(";".join(auteurs))
    
def _author_affs(e, k):
    s = ";".join( [ k for k in flatten([ v['affiliations'] for v in  e['author'] ]) if k is not None ] )
    return clean(s)
    
def _refBibAuteurs(article, k) :
    
    auteurs = []
    for e in article.get('refBibs', [] ):
        for a in e.get('author', [] ):
            auteurs.append( _auteur(a['name']) )
    auteurs = [ v for v in auteurs if len(v)> 2 ]

    s =  ";".join( auteurs )
    return clean(s)

    
def _categories(article, k) :
    l = set()
    for e in article.get('categories', [] ):
        for a in article['categories'][e]:
            cat = a[3:] if "-" in a[0:4] else a
            cat = cat.strip().lower().replace('&', ',').replace(' and ', ',').replace(' et ', ',')
            for b in cat.split(','):
                l.add( b.strip() )
    return clean( ";".join( l ) )

    
def clean(s):
    s = s.replace(',', '')
    return s
    
def flatten(l):

    for el in l:
        if isinstance(el, collections.Iterable) and not isinstance(el, basestring):
            for sub in flatten(el):
                yield sub
        else:
            yield el

SHAPES = {
    "article" : u"square",
    "refBibAuteurs" : u"diamond",
    "auteurs" : u"circle",
    "keywords" : u"triangle-top",
    "categories" : u"triangle-bottom",
 }

        
COLS = [
    #( api name, func, csv syntax, csv name )
    ('genre', _list , "", "genre"),
    ('title', _key  , "", "title"),
    ('publicationDate', _key  , "", "publicationDate"),
    ('ark', _key  , "", "ark"),
    ('corpusName', _key , "",  "corpusName" ),
    ('', _label  , "",  "label"),
    ('', _fulltext, "", "fulltext"),
    ('', _document, "", "document"),
    ('abstract', _abstract , "", "text_abstract"),
    ('id', _key, "#", "id"),
    ('doi', _key, "", "doi"),
    ('author_names', _author_names ,  "%+", "auteurs"),
    ('score', _key , "", "score"),
    ('keywords', _keywords ,  "%+", "keywords"),
    ('originalGenre', _list  , "",  "originalGenre"),
    ('refBibAuteurs', _refBibAuteurs, "%+", "refBibAuteurs"),
    ('categories', _categories  ,  "%+", "categories"),
    ('pmid', _key  , "", "pmid"),
    ('shape', lambda e,k: SHAPES.get('article', u"circle")  ,  "", "shape"),
 ]

"""
    ('author_affiliations', _author_affs ,  "%+author_affiliations"),
    ('namedEntities', ),
    ('annexes', ),
    ('metadata', ),
    ('serie', ),
    ('host', ),
    ('enrichments', ),
    ('categories', ),
    ('qualityIndicators', ),
    ('doi', ),
    ('language', ),
    ('copyrightDate', ),
    ('arkIstex', ),
    ('refBibs', ),
"""


_COLORED = u"""
_ article_categories, color[#CCC],	width[1], line[dashed]
_ article_refBibAuteurs, color[#666], width[1], line[plain]
_ article_auteurs, color[#555], width[3], line[plain]
_ article_keywords,	color[#EEE], width[1], line[plain]

@keywords: #label, shape[triangle-top], color[#EEE]	
@refBibAuteurs: #label, shape[diamond]	
@auteurs: #label, shape[circle], size[1.3]	
@categories: #label, shape[triangle-bottom]
"""

def get_schema():           
    # basic
    SCHEMA = [ [ "@%s: #label" % k , "shape[%s]" %v ]  for k,v in SHAPES.items() if k != "article"]
    # colored
    SCHEMA = [ e.split(',') for e in _COLORED.split("\n") if len(e) ]

    headers = [ "%s%s" % (e[2],e[3]) for e in COLS ]
    headers[0] = "@article: %s" % headers[0]
    headers = SCHEMA + [headers]
    print("called,", headers)
    return headers

def to_istex_url(q, field, size=10):
    q = q.encode("utf8")
    if field == "auteurs":
        qurl = "(%s)" % urllib.quote_plus("author.name:\"%s\"" % q )
    elif field == "refBibAuteurs":
        qurl = "(%s)" % urllib.quote_plus("refBibs.author.name:\"%s\"" % q )
    elif field == "keywords":
        qurl = "(%s)" % urllib.quote_plus("keywords.teeft:\"%s\"" % q )
    else:
        qurl = urllib.quote_plus( "%s" % q )

    url = "https://api.istex.fr/document/?q=%s&facet=corpusName[*]&size=%s&rankBy=qualityOverRelevance&output=*&stats" % ( qurl, size )

    if field == "istex":
        url = q

    return url


def request_api(url, headers=None):
    if not headers :
        headers = get_schema()
        
    if url :
        print "requesting %s" % url
        data = requests.get(url).json()
        rows = [ [  e[1](hit, e[0]) for e in COLS ] for hit in data['hits'] ]
        return headers, rows

    else :
        return [], []


def request_api_to_graph(gid, url, graph=None):
    headers = None if graph is None else graph_to_calc_headers(graph)
    headers, rows = request_api(url, )
    #print "HEADERS \n", headers
    #print "ROWS \n", rows
    bot = BotaIgraph(directed=True)
    botapad = Botapad(bot , gid, "", delete=False, verbose=True, debug=False)
    botapad.parse_csvrows( headers + rows, separator='auto', debug=False)
    graph = bot.get_igraph(weight_prop="weight")
    
    return graph



def to_csv(headers, rows):
    out = StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL)
    writer.writerows( headers )

    for row in rows :
        writer.writerow(row )

    return out.getvalue()


def graph_to_calc_headers(graph):

    headers = []        
    comments = [
            [ "! %s  V:%s E:%s" % ( graph['properties']['name'], graph.vcount(), graph.ecount())  ],
            [ ], ] + [  ["! %s" % json.dumps(graph['queries'])  ] ]
            
    nodetypes = [ e['name'] for e in graph['nodetypes']]
    for k in nodetypes:
        if k != "article":
            headers.append(["@%s: #label" % k, "shape[%s]" % SHAPES.get(k, "")])

    headers = comments + headers + [[],[]]
    keys = []
    for i,col in enumerate(COLS):
        col = col[3]
        key = ""
        if i == 0 :
            key = "@article:"
        isindex = col == "id"
        isproj = col in nodetypes
        key = "%s%s%s%s%s" % (key, "#" if isindex else "", "%+" if isproj else "", "", col)
        keys.append(key)

    headers = headers + [keys] 
    return headers
    
def graph_to_calc(graph):
    
    headers = graph_to_calc_headers(graph)
    rows = []

    nodetypes = [ e['name'] for e in graph['nodetypes']]
    nodetypes_idx = { e['uuid']:e for e in graph['nodetypes'] }

    articles = [ v for v in graph.vs if nodetypes_idx[v['nodetype']]['name'] == "article" ]

    for v in articles:
        row = []
        for i, col in enumerate(COLS):
            col = col[3]
            isindex = col == "id"
            isproj = col in nodetypes
            
            #print col, isindex, isproj, nodetypes_idx[v['nodetype']]['name'], v["properties"]['label']

            if not isproj:
                row.append(v['properties'][col])
            else:
                cell = []
                for e in v.neighbors():
                    n = nodetypes_idx[e['nodetype']]['name']
                    if n == col :
                        cell.append(e['properties']['label'])
                row.append(';'.join(cell))
        rows.append(row)
    return headers, rows

    
def pad_to_graph(gid, url):
    bot = BotaIgraph(directed=True)
    botapad = Botapad(bot , gid, "", delete=False, verbose=True, debug=False)
    #botapad.parse(url, separator='auto', debug=app.config['DEBUG'])
    botapad.parse(url, separator='auto', debug=False)
    graph = bot.get_igraph(weight_prop="weight")
    graph['starred'] = []
    graph['queries'] = []
    
    return graph
    
    

