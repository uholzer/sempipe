#!/usr/bin/python3

import argparse
import SemPipe
from SemPipe import Project
from SemPipe.commonargs import *

parser = argparse.ArgumentParser(description='SemPipe: Dump project data')
set_commonargs(parser)

args = parser.parse_args()

p = project_by_args(args)

print(p.g.serialize(format='nquads').decode("UTF-8"))

p.close()

