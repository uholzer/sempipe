#!/usr/bin/python3

import argparse
import SemPipe
from SemPipe import Project
from SemPipe.commonargs import *

parser = argparse.ArgumentParser(description='SemPipe: publish resources.')
set_commonargs(parser)

args = parser.parse_args()

p = project_by_args(args)
print("Publishing {}".format(SemPipe.path2fileurl(".", directory=True)))
p.publish()

