import os
import struct
import array
import sys

import drm

uint32 = struct.Struct("<I").unpack_from
uint16 = struct.Struct("<H").unpack_from

def read_scenarios(db, scndb, scndb_root):
	r = []
	root = scndb[scndb_root]
	a = array.array("I")
	a.frombytes(root.payload)
	assert a[0] == len(a)-1
	scn_ids = list(a[1:])

	for scn_id in scn_ids:
		#r = drm.Reference(scndb, db.index[7, scn_id][2])
		r = db.lookup(7, scn_id)
		script_id = r.access(uint32, 0)[0]
		count_a = r.access(uint32, 4)[0]
		entries_a = r.deref(8)
		count_b = r.access(uint32, 12)[0]

		lines = []

		for ia in range(count_a):
			entry_a = entries_a.add(ia*8)
			name = entry_a.deref(0)
			num4 = entry_a.access(uint16, 4)[0]
			num6 = entry_a.access(uint16, 6)[0]
			name = name.access_null_terminated().decode("ascii") if name else "(unnamed)"
			lines.append("{:04x} {:04x} {}".format(num4, num6, name))
		yield scn_id, count_a, count_b, lines

if __name__ == '__main__':
	db = drm.DB("pc-w/")
	scndb, scndb_root, _ = db.load("scenario_database.drm")
	for scn_id, count_a, count_b, lines in read_scenarios(db, scndb, scndb_root):
		for i, l in enumerate(lines):
			if i:
				print("             "+l)
			else:
				print("{:06x} {:2x} {:2x} {}".format(scn_id, count_a, count_b, l))
