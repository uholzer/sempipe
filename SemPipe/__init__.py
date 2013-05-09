import sys
import os
import os.path
import shutil
import urllib.parse
import urllib.request
import subprocess
import re
import collections

from lxml import etree

import rdflib
from rdflib.graph import Graph, ConjunctiveGraph, ReadOnlyGraphAggregate
from rdflib import plugin
from rdflib.collection import Collection
from rdflib.store import Store, NO_STORE, VALID_STORE
from rdflib.namespace import Namespace
from rdflib.term import Literal, URIRef, BNode, Variable
from rdflib import RDF as rdf
#from tempfile import mkdtemp

import RDFFresnel as Fresnel

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

HostedSpace = collections.namedtuple('HostedSpace', ["baseURI","mapTo","index","htaccess"]);

class Project:

    def __init__(self, uri, storePath):
        if (uri[-1] != "/"):
            raise SemPipeException("A Module must be a directory and its URI must end with a /")

        self.n = URIRef(uri)

        self.g = ConjunctiveGraph('IOMemory')
        self.storePath = storePath
        if storePath and os.path.exists(storePath+"/store.trix"):
            self.g.parse(storePath + "/store.trix", format='trix')
            self.confGraph = self.g.get_context(URIRef("sempipe:confgraph"))
            #self.storePath = storePath
            ## Get the Sleepycat plugin.
            #self.store = plugin.get('Sleepycat', Store)('rdfstore')

            ## Open previously created store, or create it if it doesn't exist yet
            #self.g = ConjunctiveGraph(store="Sleepycat",
            #               identifier = URIRef(self.default_graph_uri))
            ##path = mkdtemp()
            #rt = self.g.open(self.storePath, create=False)
            #if rt == NO_STORE:
            #    # There is no underlying Sleepycat infrastructure, create it
            #    self.g.open(self.storePath, create=True)
            #else:
            #    assert rt == VALID_STORE, "The underlying store is corrupt"
        else:
            #Aggregate graphs
            self.confGraph = self.g.get_context(URIRef("sempipe:confgraph"))
            self._loadconf()
            for graph in self.confGraph.objects(self.n, semp.dataGraph):
                self.loadData(graph)
        for updateList in self.confGraph.objects(self.n, semp.update):
            for updateInstruction in Collection(self.confGraph, updateList):
                self.updateGraph(str(updateInstruction))
        self.commit()
        # Cache HostedSpaces
        self.hostedSpaces = []
        res = self.confGraph.query("""
            SELECT ?baseURI ?mapTo ?index ?htaccess {
                ?baseURI a semp:HostedSpace ;
                semp:mapTo ?mapTo ;
                semp:mapIndexTo ?index ;
                semp:mapHTAccessTo ?htaccess .
            }
        """, initNs={"semp": semp})
        for s in res:
            self.hostedSpaces.append(HostedSpace._make(s))

    def __str__(self):
        return str(self.n)
            
    def __repr__(self):
        return "{0}({1},{2})".format(self.__class__.__name__, repr(self.n), repr(self.storePath))

    def _loadconf(self, uri=None):
        """Loads a graph and all config-graphs it references as configuration graphs

        @param uri: a URIRef, defaults to self.n+SempPipe.conffilename"""
        uri = uri or URIRef(self.n + conffilename)

        if self.g.get_context(uri):
            print("ConfGraph {} already in database".format(uri), file=sys.stderr)
            return

        print("Loading {} as config graph".format(uri), file=sys.stderr)
        newgraph = self.g.parse(uri, format="n3")
        self.confGraph += newgraph
        self.confGraph.add((uri, rdf.type, semp.ConfGraph))
        imports = set(newgraph.objects(uri, semp.confGraph))
        imports |= set(newgraph.objects(self.n, semp.confGraph))
        imports = filter(lambda x: not self.g.get_context(x), imports)
        #Recursively load additional graphs
        for imp in imports:
            self._loadconf(imp)

    def loadData(self, url):
        """Loads a data graph"""
        return parse(self.g, url)

    def updateGraph(self, sparql):
        try:
            self.g.update(sparql)
        except:
            raise SemPipeException("Update instruction failed:\n{}".format(str(sparql)))

    def hostedSpace(self, resource, reverse=False):
        """Picks the best matching hostedSpace for the given resource.

        If reverse is set, resource is considered to be a path
        relative to the buildDir and the corresponding URIRef is
        returned."""
        if reverse:
            hostedSpaces = filter(lambda s: resource.startswith(self.buildDir + s.mapTo), self.hostedSpaces)
        else:
            hostedSpaces = filter(lambda s: resource.startswith(s.baseURI), self.hostedSpaces)
        # Find the best match, which is the most specific one:
        try:
            return max(hostedSpaces, key=lambda s: len(s.baseURI))
        except ValueError:
            raise SemPipeException("No hosted space found for {}".format(resource))

    def contentLocation(self, base, ending):
        if str(base)[-1] == '/':
            index = self.hostedSpace(base).index
            return str(base) + index + ending
        else:
            return str(base) + ending

    @property
    def buildDir(self):
        return next(self.confGraph.objects(self.n, semp.buildDir))

    def buildLocation(self, resource):
        """Determines the filename in the build directory
        corresponding to a URI."""
        hs = self.hostedSpace(resource)
        return self.buildDir + hs.mapTo + resource[len(hs.baseURI):]

    def buildLocationToResource(self, buildLocation):
        """Determines the filename in the build directory
        corresponding to a URI."""
        if not buildLocation.startswith(self.buildDir):
            raise SemPipeException("{} is not in buildDir".format(buildLocation))
        
        hs = self.hostedSpace(buildLocation, reverse=True)
        return URIRef(hs.baseURI + buildLocation[len(self.buildDir + hs.mapTo):])

    def copy(self, source, dest):
        """Publish a resource by copying a file

        Note that dest is the URI where the resource should be
        published, the corresponding directory in the build directory
        is derived automatically."""
        dest = self.buildLocation(dest)
        print("copy {0} to {1}".format(source, dest), file=sys.stderr)
        directory = dest.rsplit("/",1)[0]
        directory = fileurl2path(directory)
        print("  Making shure directory {0} exists".format(directory), file=sys.stderr)
        os.makedirs(directory, mode=0o777, exist_ok=True)
        shutil.copy(fileurl2path(source), fileurl2path(dest))
        print("  done", file=sys.stderr)

    def write(self, dest, data):
        """Publishes a file with contents data"""
        dest = self.buildLocation(dest)
        print("writing data to {0}".format(dest), file=sys.stderr)
        directory = dest.rsplit("/",1)[0]
        directory = fileurl2path(directory)
        print("  Making shure directory {0} exists".format(directory), file=sys.stderr)
        os.makedirs(directory, mode=0o777, exist_ok=True)
        with open(fileurl2path(dest), mode="wb") as f:
            f.write(data)
        print("  done", file=sys.stderr)

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

        representations = self.confGraph.objects(resource, semp.representation)
        for r in representations:
            content_type = next(self.confGraph.objects(r, semp["content-type"]))
            try:
                source = next(self.confGraph.objects(r, semp.source))
            except(StopIteration):
                source = None
            try:
                language = next(self.confGraph.objects(r, semp.language))
            except(StopIteration):
                language = None
            try:
                quality = next(self.confGraph.objects(r, semp.quality))
            except(StopIteration):
                quality = None
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
                #Fresnel.prettify(tree) # results in bad whitespace
                self.write(contentLocation, etree.tostring(tree,encoding="UTF-8",xml_declaration=True))
            elif semp.Serialize in self.confGraph.objects(r, semp.buildCommand):
                graph = self.g.get_context(resource)
                self.write(contentLocation, graph.serialize())
            else:
                raise SemPipeException("Failed to produce representation {0} of {1}".format(r, resource))

            try:
                xslt_files = Collection(self.confGraph, next(self.confGraph.objects(r, semp.transformation)))
                buildloc = self.buildLocation(contentLocation)
                for xslt_file in xslt_files:
                    command = ["xsltproc",
                               "--output", fileurl2path(buildloc),
                               fileurl2path(str(xslt_file)),
                               fileurl2path(buildloc)]
                    print("Running transformation", *command, file=sys.stderr)
                    subprocess.call(command)
            except (StopIteration):
                pass

        #write typemap
        typemap = self.typemap(resource)
        if typemap is not None:
            self.write(resource, typemap)
            

    def typemap(self, resource):
        """
        Returns the contents of a type-map file for all
        representations of the given resource. Returns None if no
        typemap is necessary.
        """
        representations = sorted(self.confGraph.objects(resource, semp.representation))
        typemap_url = lambda url: str(url).rsplit("/", 1)[-1]
        typemap = ["URI: {}\n\n".format(typemap_url(resource))]
        typemap_needed = False
        for r in representations:
            content_type = next(self.confGraph.objects(r, semp["content-type"]))
            try:
                source = next(self.confGraph.objects(r, semp.source))
            except(StopIteration):
                source = None
            try:
                language = next(self.confGraph.objects(r, semp.language))
            except(StopIteration):
                language = None
            try:
                quality = next(self.confGraph.objects(r, semp.quality))
            except(StopIteration):
                quality = None
            contentLocation = URIRef(self.contentLocation(resource, self.defaultEnding(content_type, language)))

            typemap.append("URI: {}\n".format(typemap_url(contentLocation)))
            typemap.append("Content-type: {}".format(content_type))
            if quality is not None:
                typemap[-1] += "; q={}\n".format(quality)
                typemap_needed = True
            else:
                typemap[-1] += "\n"
            if language is not None:
                typemap.append("Content-language: {}\n".format(language))
            typemap.append("\n")

        if typemap_needed:
            return "".join(typemap).encode("UTF-8")
        else:
            return None


    def defaultEnding(self, content_type=None, language=None):
        cts = { "application/rdf+xml": ".rdf", "application/xhtml+xml": ".xhtml", "text/html": ".html", None: "" }
        if content_type:
            typeendings = list(self.confGraph.objects(URIRef("http://purl.org/NET/mediatypes/" + content_type), semp.defaultExtension))
            if len(typeendings) > 1:
                raise SemPipeException("ambiguous extension for content-type {} in confGraph.".format(content_type))
            elif len(typeendings) < 1:
                raise SemPipeException("No extension for content-type {} found".format(content_type))
            else:
                typeending = typeendings[0]
        else:
            typeending = ""
        return ("." + language if language else "") + "." + typeending

    def write_htaccess(self):
        """Writes all required .htaccess files."""

        # First generate the directives for each resource
        filesinfo = [];
        resources = self.resources
        for resource in resources:
            info = [];
            filesinfo.append((resource, info));
            if self.typemap(resource) is not None:
                info.append("SetHandler type-map\n")

        # Generate the .htaccess files
        htaccessfiles = dict()
        for resource, info in filter(lambda x: x[1], filesinfo):
            directory, filename = resource.rsplit("/", 1)
            ht = htaccessfiles.setdefault(directory, [])
            ht.append('<Files "{}">\n'.format(filename))
            ht += info
            ht.append('</Files>\n')

        for directory, ht in htaccessfiles.items():
            print("Writing a .htaccess in {}".format(directory), file=sys.stderr)
            filename = self.hostedSpace(resource).htaccess
            self.write(directory + "/" + filename, "".join(ht).encode("UTF-8"))

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
            print("Running {}".format(command[0]), file=sys.stderr)
            subprocess.call(command)

    @property
    def resources(self):
        return self.confGraph.subjects(rdf.type, semp.Resource)

    def commit(self):
        self.g.commit()
        if self.storePath:
            self.g.serialize(destination=self.storePath+"/store.trix", format='trix', encoding='UTF-8')

    def serialize(self):
        return self.g.serialize()

    def close(self):
        self.g.close()


