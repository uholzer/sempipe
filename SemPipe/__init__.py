import os
import os.path
import shutil
import urllib.parse
import urllib.request
import subprocess

from lxml import etree

import rdflib
from rdflib.graph import Graph, ConjunctiveGraph, ReadOnlyGraphAggregate
from rdflib import plugin
from rdflib.store import Store, NO_STORE, VALID_STORE
from rdflib.namespace import Namespace
from rdflib.term import Literal
from rdflib.term import URIRef
from rdflib import RDF as rdf
#from tempfile import mkdtemp

import Fresnel

# We should not use SQLite, since
# https://groups.google.com/forum/?fromgroups=#!topic/rdflib-dev/Cv0cekvDBnY

plugin.register(
    'sparql', rdflib.query.Processor,
    'rdfextras.sparql.processor', 'Processor')
plugin.register(
    'sparql', rdflib.query.Result,
    'rdfextras.sparql.query', 'SPARQLQueryResult')

semp = Namespace("http://www.andonyar.com/rec/2012/sempipe/voc#")

class SemPipeException(Exception):
    pass

def fileurl2path(url):
    url = urllib.parse.urlparse(url)
    if not url.scheme == "file":
        raise SemPipeException("source must be a file")
    return urllib.request.url2pathname(url.path)

def path2fileurl(path, directory=False):
    path = os.path.abspath(path)
    url = "file://" + urllib.request.pathname2url(path)
    if directory and url[-1] != "/":
        url += "/"
    return url

conffilename = "sempipeconf.n3"

class Project(URIRef):

    def __init__(self, uri, storePath):
        if (uri[-1] != "/"):
            raise SemPipeException("A Module must be a directory and its URI must end with a /")
        super().__init__(uri)

        self.storePath = storePath
        # Get the Sleepycat plugin.
        self.store = plugin.get('Sleepycat', Store)('rdfstore')

        self.default_graph_uri = "http://andonyar.com/foo"

        # Open previously created store, or create it if it doesn't exist yet
        self.g = ConjunctiveGraph(store="Sleepycat",
                       identifier = URIRef(self.default_graph_uri))
        #path = mkdtemp()
        rt = self.g.open(self.storePath, create=False)
        if rt == NO_STORE:
            # There is no underlying Sleepycat infrastructure, create it
            self.g.open(self.storePath, create=True)
        else:
            assert rt == VALID_STORE, "The underlying store is corrupt"

        #Aggregate graphs
        self.confGraphsList = [] # We have our own list, because ReadOnlyGraphAggregate.contexts has empty return value
        self.confGraph = None
        #Following does not work, constructor does not accept an empty list
        #self.confGraph = ReadOnlyGraphAggregate(self.confGraphsList)
        self._loadconf()

    def _loadconf(self, uri=None):
        """Loads a graph and all config-graphs it references as configuration graphs

        @param uri: a URIRef, defaults to self+SempPipe.conffilename"""
        uri = uri or URIRef(self + conffilename)

        if self.g.get_context(uri):
            print("ConfGraph {} found in database".format(uri))
            newgraph = self.g.get_context(uri)
        else:
            print("Loading {} as config graph".format(uri))
            newgraph = self.g.parse(uri, format="n3")
            self.commit()
        self.confGraphsList += [newgraph]
        self.confGraph = ReadOnlyGraphAggregate(self.confGraphsList)
        qres = self.confGraph.query(
            """SELECT DISTINCT ?cg
               WHERE {
                  ?cg semp:subgraphOf semp:ConfigGraph .
               }""",
            initNs={ "semp": semp }
        )
        #Recursively load additional graphs if not already done so
        alreadyLoaded = set([confGraph.identifier for confGraph in self.confGraphsList])
        for row in qres.result:
            if row[0] not in alreadyLoaded:
                self.loadconf(row[0])

    @property
    def buildDir(self):
        return next(self.confGraph.objects(self, semp.buildDir))

    def buildLocation(self, resource):
        return self.buildDir + "/" + resource

    def copy(self, source, dest):
        """Publish a resource by copying a file

        Note that dest is the URI where the resource should be
        published, the corresponding directory in the build directory
        is derived automatically."""
        dest = self.buildLocation(dest)
        print("copy {0} to {1}".format(source, dest))
        directory = dest.rsplit("/",1)[0]
        directory = fileurl2path(directory)
        print("  Making shure directory {0} exists".format(directory))
        os.makedirs(directory, mode=0o777, exist_ok=True)
        shutil.copy(fileurl2path(source), fileurl2path(dest))
        print("  done")

    def write(self, dest, data):
        """Publishes a file with contents data"""
        dest = self.buildLocation(dest)
        print("writing data to {0}".format(dest))
        directory = dest.rsplit("/",1)[0]
        directory = fileurl2path(directory)
        print("  Making shure directory {0} exists".format(directory))
        os.makedirs(directory, mode=0o777, exist_ok=True)
        with open(fileurl2path(dest), mode="wb") as f:
            f.write(data)
        print("  done")

    def buildResource(self, resource):
        """Looks up the description of the resource and builds it

        Creates all representations of the resource and adds
        information to the .htaccess if required.
   
        semp:Reource
            type of a Resource
            semp:subject
                What the page is mainly about. This is used by
                semp:Render to know which one is the root node.
            semp:source
                points to a source file
            semp:representation
                A variant of the resource, obtainable by content nogtiation
                semp:content-type
                    indicates the targetted content type
                semp:buildCommand
                    tells how to build the representation.
                    Use semp:Render to render with fresnel Lenses and
                    an XSLT. Use semp:Raw to just take the surce file.
        semp:content-type
            used on a source file or representation to indicate the content type
        """

        source = next(self.confGraph.objects(resource, semp.source))
        representations = self.confGraph.objects(resource, semp.representation)
        for r in representations:
            content_type = next(self.confGraph.objects(r, semp["content-type"]))
            try:
                language = next(self.confGraph.objects(r, semp.language))
            except(StopIteration):
                language = None
            contentLocation = URIRef(resource + self.defaultEnding(content_type, language))
            if semp.Raw in self.confGraph.objects(r, semp.buildCommand):
                self.copy(source, contentLocation)
            elif semp.Render in self.confGraph.objects(r, semp.buildCommand):
                fresnelGraph = Graph()
                fresnelGraph.parse(next(self.confGraph.objects(r, semp.fresnelGraph)), format="n3")
                instanceGraph = Graph()
                instanceGraph.parse(source)
                ctx = Fresnel.Context(fresnelGraph=fresnelGraph, instanceGraph=instanceGraph)
                box = Fresnel.ContainerBox(ctx)
                box.append(next(self.confGraph.objects(resource, semp.subject)))
                box.select()
                box.format()
                tree = box.transform()
                self.write(contentLocation, etree.tostring(tree, pretty_print=True))
            else:
                raise SemPipeException("Failed to produce representation {0} of {1}".format(r, resource))

    def defaultEnding(self, content_type=None, language=None):
        cts = { "application/rdf+xml": ".rdf", "text/html": ".html", None: "" }
        return cts[content_type] + ("." + language if language else "")

    @property
    def resources(self):
        return self.confGraph.subjects(rdf.type, semp.Resource)

    def commit(self):
        self.g.commit()

    def serialize(self):
        return self.g.serialize()

    def close(self):
        self.g.close()


