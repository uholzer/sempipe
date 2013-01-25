#!/usr/bin/python3

import SemPipe
from SemPipe import Project

print("Building {}".format(SemPipe.path2fileurl(".", directory=True)))
p = Project(SemPipe.path2fileurl(".", directory=True), "./sempipe_store")
resources = p.resources

print(p.g.serialize(format='trix').decode("UTF-8"))

p.close()

