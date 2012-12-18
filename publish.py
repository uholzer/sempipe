#!/usr/bin/python3

import SemPipe
from SemPipe import Project

print("Publishing {}".format(SemPipe.path2fileurl(".", directory=True)))
p = Project(SemPipe.path2fileurl(".", directory=True), "./sempipe_store")
p.publish()

