#-*- coding:utf-8 -*-

from flask import Flask, Response, make_response, g, current_app, request
from flask import render_template, render_template_string, abort, redirect, url_for,  jsonify


import sys
#import csv
import unicodecsv as csv
import requests
import collections
from StringIO import StringIO

app = Flask(__name__)
app.config['DEBUG'] = False

CALC_URL = "http://calc.padagraph.io/export-cillex-csv"


# parse response attributes
_key = lambda e,k : e.get(k)
_label = lambda e,k : e.get('title')[:12]
_abstract = lambda e,k : e.get('abstract')
_list = lambda e, k : ";".join(e.get(k))
_keywords = lambda e, k : ";".join(e['keywords']['teeft']) if 'keywords' in e else ""

def _author_names( e, k ):
    s =  ";".join( [ v['name'] for v in  e['author'] ])
    return clean(s)
    
def _author_affs(e, k):
    s = ";".join( [ k for k in flatten([ v['affiliations'] for v in  e['author'] ]) if k is not None ] )
    return clean(s)
    
def _refBibAuteurs(article, k) :
    
    auteurs = []
    for e in article.get('refBibs', [] ):
        for a in e.get('author', [] ):
            auteurs.append( a['name'] )

    s =  ";".join( auteurs )
    return clean(s)

def _categories(article, k) :
    
    l = []
    for e in article.get('categories', [] ):
        for a in article['categories'][e]:
            l.append( a[3:].strip() )

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


# csv cols

COLS = [
    ('genre', _list , "@article: title"),
    ('title', _key  ,  "genre"),
    ('corpusName', _key ,  "corpusName" ),
    ('label', _label  ,  "label"),
    ('author_names', _author_names ,  "%+ auteurs"),
    #('author_affiliations', _author_affs ,  "%+author_affiliations"),
    ('abstract', _abstract ,  "abstract"),
    ('score', _key ,  "score"),
    ('keywords', _keywords ,  "%+ keywords"),
    ('originalGenre', _list  ,  "originalGenre"),
    ('pmid', _key  ,  "pmid"),
    ('refBibAuteurs', _refBibAuteurs, "%+ refBibAuteurs"),
    ('id', _key, "#id"),
    ('shape', lambda e,k: "square"  ,  "shape"),
    ('categories', _categories  ,  "%+categories"),
 ]

"""
    ('publicationDate', ),
    ('ark', ),
    ('namedEntities', ),
    ('annexes', ),
    ('metadata', ),
    ('fulltext', ),
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


def request_api(url):
    if url : 
        data = requests.get(url).json()
        headers = [ "%s" % (e[2]) for e in COLS ]
        rows = [ [  e[1](hit, e[0]) for e in COLS ] for hit in data['hits'] ]
        return headers, rows
    else :
        return [], []

        
def to_csv(headers, rows):
    out = StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL , )
    writer.writerow( headers )

    for row in rows :
        writer.writerow(row )

    return out.getvalue()


@app.route('/csv', methods=['GET', 'POST'])
def tocsv():
    schema = """ 
@refBibAuteurs: #label, shape[triangle-top]
@auteurs: #label, shape[triangle-down]
@keywords: #label, shape[diamond]
@categories: #label, shape[diamond]
"""
    
    urls = request.form.get('urls', "").split()
    calc = request.form.get('calc', CALC_URL)
    _calc = calc.split("/")
    _calc = "/".join(_calc[:-1] + ['_'] + _calc[-1:])
    
    append = request.form.get('append', False)

    table = False
    headers, rows = (None, None)
    mode = "POST" if append else "PUT"
    graph = "http://localhost:5000/import/igraph.html?nofoot=1&s=%s&gid=cillex" % calc

        
    for url in urls:
        if not len(url) : continue
        
        headers, rows = request_api(url)

        table = headers and len(headers) > 0

        if table:
            if mode == "PUT":
                print( "* PUT %s %s " % (_calc, len(rows)) ) 
                r = requests.put(_calc, data=schema + "\n" + to_csv(headers, rows))
            if mode == "POST":
                print( "* POST %s %s " % (_calc, len(rows)) ) 
                r = requests.post(_calc, data=to_csv([], rows))
            mode = "POST"
             
    return render_template('tocsv.html',
            table=table, mode=mode,
            headers=headers, rows=rows,
            calc=calc,
            graph=graph,
            urls= " ".join( urls if len(urls) else [] )
            )


from flask_runner import Runner
def main():
    ## run the app
    print "running main"

    #build_app()

    runner = Runner(app)
    runner.run()

if __name__ == '__main__':
    sys.exit(main())



