#!/usr/bin/python

import argparse
from rdflib import URIRef
from rdflib.collection import Collection
from rdflib.graph import QuotedGraph
from sys import stdin
import logging

logging.getLogger().setLevel(logging.INFO)

parser = argparse.ArgumentParser(description='SemPipe Planner: Construct commands to build resources.')
args = parser.parse_args()

g = QuotedGraph('IOMemory', URIRef("sempipe:conf"))
g.parse(stdin, format='n3', publicID=URIRef("file:///home/urs/p/andonyar/articles/"))

def instruction_buildVar(var):
    name = g.value(var, URIRef("http://www.andonyar.com/rec/2012/sempipe/voc#name"), None, any=False)
    value = g.value(var, URIRef("http://www.andonyar.com/rec/2012/sempipe/voc#value"), None, any=False)
    assert(name and value)
    return "{}={}".format(name, value)

def instruction_build(col):
    col = Collection(g, col)
    return [ c for c in col ]

resources = g.subjects(URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), URIRef("http://www.andonyar.com/rec/2012/sempipe/voc#Resource"))
for r in resources:
    logging.info("Building resource {0}".format(r))
    instructions = []
    instructions += [
        instruction_buildVar(v) for v
        in g.objects(r, URIRef("http://www.andonyar.com/rec/2012/sempipe/voc#buildVar"))
    ]
    instructions += instruction_build(g.value(r, URIRef("http://www.andonyar.com/rec/2012/sempipe/voc#build"), None, any=False))
    print("\n".join(instructions))
   

