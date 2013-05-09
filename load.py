#!/usr/bin/python3

import argparse
import SemPipe
from SemPipe import Project
from SemPipe.commonargs import *

parser = argparse.ArgumentParser(description='SemPipe: Load graphs and process updates.')
set_commonargs(parser)

args = parser.parse_args()

p = project_by_args(args)
p.commit()
p.close()

print("Successfully loaded configuration and data for Module\n{}".format(str(p)))

