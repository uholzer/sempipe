import os
import os.path
import shutil
import urllib.parse
import urllib.request
import subprocess
import re

from lxml import etree

import rdflib
from rdflib.graph import Graph, ConjunctiveGraph, ReadOnlyGraphAggregate
from rdflib import plugin
from rdflib.collection import Collection
from rdflib.store import Store, NO_STORE, VALID_STORE
from rdflib.namespace import Namespace
from rdflib.term import Literal, URIRef, BNode, Variable
from rdflib import RDF as rdf
import rdflib_sparql
#from tempfile import mkdtemp

import Fresnel

# We should not use SQLite, since
# https://groups.google.com/forum/?fromgroups=#!topic/rdflib-dev/Cv0cekvDBnY

#plugin.register(
#    'sparql', rdflib.query.Processor,
#    'librdf_sparql.processor', 'Processor')
#plugin.register(
#    'sparql', rdflib.query.Result,
#    'librdf_sparql.results', 'SPARQLQueryResult')

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

def parse(graph, url):
    if isinstance(url, BNode):
        raise SemPipeException("Can not use BNode as URL")
    if re.match("^file:.*\.n3$", url):
        return graph.parse(url, format="n3")
    elif re.match("^file:.*\.rdf$", url):
        return graph.parse(url, format="xml")
    else:
        # Hope for automatic format guessing when using other protocols
        return graph.parse(source=url)

def multiparse(graph, urls):
    for url in urls: parse(graph, url)

conffilename = "sempipeconf.n3"

class Project(URIRef):

    def __init__(self, uri, storePath):
        if (uri[-1] != "/"):
            raise SemPipeException("A Module must be a directory and its URI must end with a /")
        super().__init__(uri)

        self.default_graph_uri = "http://andonyar.com/foo"

        if False:
            self.storePath = storePath
            # Get the Sleepycat plugin.
            self.store = plugin.get('Sleepycat', Store)('rdfstore')

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
        else:
            self.g = ConjunctiveGraph(identifier = URIRef(self.default_graph_uri))
            self.g.default_context = self.g

        #Aggregate graphs
        self.confGraphsList = [] # We have our own list, because ReadOnlyGraphAggregate.contexts has empty return value
        self.confGraph = None
        #Following does not work, constructor does not accept an empty list
        #self.confGraph = ReadOnlyGraphAggregate(self.confGraphsList)
        self._loadconf()
        for graph in self.confGraph.objects(self, semp.dataGraph):
            self.loadData(graph)
        for updateList in self.confGraph.objects(self, semp.update):
            for updateInstruction in Collection(self.confGraph, updateList):
                print("Update")
                self.updateGraph(str(updateInstruction))

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
        self.confGraph.default_context = self.confGraph
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

    def loadData(self, url):
        """Loads a data graph"""
        parse(self.g, url)

    def updateGraph(self, sparql):
        rdflib_sparql.processor.processUpdate(self.g, sparql)

    def contentLocation(self, base, ending):
        if str(base)[-1] == '/':
            return str(base) + 'index' + ending
        else:
            return str(base) + ending

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

        try:
            source = next(self.confGraph.objects(resource, semp.source))
        except(StopIteration):
            source = None
        representations = self.confGraph.objects(resource, semp.representation)
        for r in representations:
            content_type = next(self.confGraph.objects(r, semp["content-type"]))
            try:
                language = next(self.confGraph.objects(r, semp.language))
            except(StopIteration):
                language = None
            contentLocation = URIRef(self.contentLocation(resource, self.defaultEnding(content_type, language)))
            if semp.Raw in self.confGraph.objects(r, semp.buildCommand):
                self.copy(source, contentLocation)
            elif semp.Render in self.confGraph.objects(r, semp.buildCommand):
                #fresnelGraph = Graph()
                #multiparse(fresnelGraph, self.confGraph.objects(r, semp.fresnelGraph))
                #instanceGraph = Graph()
                #parse(instanceGraph, source)
                #multiparse(instanceGraph, self.confGraph.objects(r, semp.additionalData))
                fresnelGraph = self.g
                instanceGraph = self.g
                ctx = Fresnel.Context(fresnelGraph=fresnelGraph, instanceGraph=instanceGraph)
                box = Fresnel.ContainerBox(ctx)
                box.append(resource)
                box.select()
                box.portray()
                tree = box.transform()
                try:
                    xslt_file = next(self.confGraph.objects(r, semp.transformation))
                    xslt_tree = etree.parse(fileurl2path(str(xslt_file)))
                    transformation = etree.XSLT(xslt_tree)
                    tree = transformation(tree)
                except (StopIteration):
                    pass
                Fresnel.prettify(tree)
                self.write(contentLocation, etree.tostring(tree,encoding="UTF-8",xml_declaration=True))
            elif semp.Serialize in self.confGraph.objects(r, semp.buildCommand):
                graph = self.g.get_context(resource)
                self.write(contentLocation, graph.serialize())
            else:
                raise SemPipeException("Failed to produce representation {0} of {1}".format(r, resource))

    def defaultEnding(self, content_type=None, language=None):
        cts = { "application/rdf+xml": ".rdf", "text/html": ".html", None: "" }
        return cts[content_type] + ("." + language if language else "")

    def publish(self):
        import getpass
        import subprocess

        """Walks through HostedSpaces and upload the respective files
        from the build diretory.

        (Instead we should walk through the build directory. Will be
        changed later.)"""

        hostedSpacesQuery = """
        SELECT ?space ?method ?command ?invocation
        WHERE {
            ?space a semp:HostedSpace .
            ?space semp:publishMethod ?method .
            ?method semp:command ?command .
            ?method semp:invocation ?invocation .
        }"""
        askForQuery = """
        SELECT ?variable
        WHERE {
            { ?method semp:askFor ?variable . }
            UNION
            { ?method semp:askForHidden ?variable . }
        }""" 
        #?hidden
        #{ ?method semp:askFor ?variable . }
        #UNION
        #{ ?method semp:askForHidden ?variable .
        #  BIND ("true"^^xsd:boolean as ?hidden) }
        for spaceRow in self.confGraph.query(hostedSpacesQuery, initNs={"semp": semp}).bindings:
            space = spaceRow[Variable("?space")]
            method = spaceRow[Variable("?method")]
            answers = dict()
            for question in self.confGraph.query(askForQuery, initNs={"semp": semp}, initBindings={"method": method}).bindings:
                answers[question[Variable("?variable")]] = getpass.getpass("{} for method {}".format(question[Variable("?variable")], method))
            spacedir = self.buildLocation(space)
            command = []
            for arg in Collection(self.confGraph, spaceRow[Variable("command")]):
                command.append(str(arg).format("",fileurl2path(spacedir),str(space),**answers))
            print("Running {}".format(command[0]))
            subprocess.call(command)

    @property
    def resources(self):
        return self.confGraph.subjects(rdf.type, semp.Resource)

    def commit(self):
        self.g.commit()

    def serialize(self):
        return self.g.serialize()

    def close(self):
        self.g.close()


