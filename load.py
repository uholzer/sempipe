#!/usr/bin/python3

import SemPipe
from SemPipe import Project

p = Project(SemPipe.path2fileurl(".", directory=True), "./sempipe_store")
p.commit()
p.close()

print("Successfully loaded configuration and data for Module\n{}".format(str(p)))

