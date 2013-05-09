"""Handling arguments common to all SemPipe command line tools"""

import SemPipe
import os

def set_commonargs(argparser):
    argparser.add_argument('-s', '--store', metavar='DIR', dest='store',
                           help='''Store internal RDF data in this directory. Useful if
                                   one does processing in multiple steps. Note:
                                   already existing graphs will not be reloaded.
                                   Clear the contents of this directory before rebuilding.''')

def project_by_args(args):
    if args.store:
        if not os.path.exists(args.store):
            os.mkdir(args.store)
        if not os.path.isdir(args.store):
            print("{} exists, but is not a directory", file=sys.stderr)
            exit(1) #XXX: Maybe we want to raise an exception instead

    return SemPipe.Project(SemPipe.path2fileurl(".", directory=True), args.store)
