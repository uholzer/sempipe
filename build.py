#!/usr/bin/python3

import argparse
import SemPipe
from SemPipe import Project
from SemPipe.commonargs import *

parser = argparse.ArgumentParser(description='SemPipe: Build the project.')
set_commonargs(parser)

args = parser.parse_args()

p = project_by_args(args)

resources = p.resources
for r in resources:
    print("Building resource {0}".format(r))
    p.buildResource(r)
p.write_htaccess()

p.commit()
p.close()

