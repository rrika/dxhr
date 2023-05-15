import sys, os
import os.path
import drm

def findstrings(data):
	x = False
	j = None
	for i, k in enumerate(data):
		y = k >= 16 and k < 128
		if y and not x:
			j = i
		elif x and not y:
			yield (j, i)
		x = y
	if x:
		yield (j, len(data))

assert list(findstrings(b"xxx\0\0\0xxx")) == [(0, 3), (6, 9)]

fnames = sys.argv[1:]
basepath = "./pc-w"
db = drm.DB(basepath)

cutoff = 8

for fname in fnames:
	fname = os.path.relpath(fname, basepath)
	sections, rootsectionindex, _ = db.load(fname)
	for i, section in enumerate(sections):
		print("{}/{:x}".format(fname, i))
		for (a, b) in findstrings(section.payload):
			if b-a >= cutoff:
				print("   ", section.payload[a:b].decode("utf-8"))

