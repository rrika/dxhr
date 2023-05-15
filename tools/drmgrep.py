import sys, os
import os.path
import drm

term = sys.argv[1]
fnames = sys.argv[2:]

if term[:2] == "0x":
	import binascii
	term = binascii.unhexlify(term[2:])
else:
	term = term.encode("utf-8")

print("looking for", term, "in", len(fnames), "file" if len(fnames)==1 else "files")

basepath = "./pc-w"
db = drm.DB(basepath)

for fname in fnames:
	fname = os.path.relpath(fname, basepath)
	sections, rootsectionindex = db.load(fname)
	matches = []
	for i, section in enumerate(sections):
		try:
			j = section.payload.index(term)
			matches.append((i, j))
		except ValueError:
			pass
	if matches:
		print(fname)
		for i, j in matches:
			print("  section {:x} offset {:x}".format(i, j))
