#!/usr/bin/python3

import SemPipe
from SemPipe import Project

print("Building {}".format(SemPipe.path2fileurl(".", directory=True)))
p = Project(SemPipe.path2fileurl(".", directory=True), "./sempipe_store")
resources = p.resources
for r in resources:
    print("Building resource {0}".format(r))
    p.buildResource(r)
p.write_htaccess()

p.commit()
p.close()

