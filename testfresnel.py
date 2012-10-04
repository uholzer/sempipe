from rdflib.graph import Graph, ConjunctiveGraph, ReadOnlyGraphAggregate
from rdflib.term import URIRef, BNode, Literal
from rdflib import Namespace, RDF
import Fresnel

fresnelGraph = Graph()
fresnelGraph.parse("testfresnel.n3", format="n3")

FOAF = Namespace("http://xmlns.com/foaf/0.1/")

instanceGraph = Graph()
donna = BNode()
instanceGraph.add((donna, RDF.type, FOAF["Person"]))
instanceGraph.add((donna, FOAF["nick"], Literal("donna", lang="foo")))
instanceGraph.add((donna, FOAF["name"], Literal("Donna Fales")))

l = Fresnel.Lens(fresnelGraph, URIRef("file:///home/urs/p/sempipe/testfresnel.n3#knowsLens"))

print("I obtained a lens: {0}".format(l))

print("Create a ContainerBox")
context = Fresnel.Context(fresnelGraph=fresnelGraph, instanceGraph=instanceGraph)
box = Fresnel.ContainerBox(context)
box.append(donna)
print("calling select:")
box.select()
print("result:")
print(box)

