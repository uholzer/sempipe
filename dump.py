#!/usr/bin/python3

import SemPipe
from SemPipe import Project

p = Project(SemPipe.path2fileurl(".", directory=True), "./sempipe_store")
resources = p.resources

print(p.g.serialize(format='trix').decode("UTF-8"))

p.close()

