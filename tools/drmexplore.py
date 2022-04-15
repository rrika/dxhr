#!/usr/bin/env python3
import sys, os, struct
import os.path
import drm

uint32 = struct.Struct("<I").unpack_from
uint16 = struct.Struct("<H").unpack_from

typenames = {
	0: "Generic",
	1: "Empty",
	2: "Animation",
	5: "RenderResource",
	6: "FMODSoundBank",
	7: "DTPData",
	8: "Script",
	9: "ShaderLib",
	10: "Material",
	11: "Object",
	12: "RenderMesh",
	13: "CollisionMesh",
	14: "StreamGroupList"
}

subtypenames = {
	5:  "Texture",
	13: "Sound",
	24: "RenderTerrain",
	26: "RenderModel",
	27: "?",
	40: "SmartScript",
	41: "Scaleform",
	42: "Conversation",
	50: "CameraShake"
}

def oneline_summary(fname, sections, i, section):

	sectype = section.typeid
	subtype = section.subtypeid

	desc = typenames.get(sectype, str(sectype))
	if subtype in subtypenames:
		desc += " ({})".format(subtypenames[subtype])
	else:
		desc += " {:x}".format(subtype)

	desc += " {:x}".format(section.s_id)

	if sectype == 6: # FMODSoundBank
		desc += " "
		fmod = drm.Reference(sections, section, 16)
		num_files = fmod.access(uint32, 4)[0]
		fmod.offset += 48
		for j in range(num_files):
			size = fmod.access(uint16, 0)[0]
			name = section.payload[fmod.offset+2:fmod.offset+32].decode("utf-8")
			if j:
				desc += ","
			desc += name
			fmod.offset += size

	print("{}/{:x}: {} unk6:{:x} ({:x} bytes)".format(fname, i, desc, section.unk6, len(section.payload)))

def print_references(i, section):
	for patchsite, info in section.fixupinfo.items():
		if isinstance(info[1], tuple):
			ty, s_id = info[1]
			assert info[2] == 0
			print("{:x} -> ({} {:x})".format(patchsite, typenames[ty], s_id))
		else:
			print("{:x} -> ({:x}: {:x})".format(patchsite, info[1], info[2]))

def build_ref_index(sections):
	index = {}
	for i, section in enumerate(sections):
		for r, (kind, target, offset) in section.fixupinfo.items():
			if isinstance(target, int):
				index.setdefault((target, offset), []).append((i, r))
	return index

def dump32_internal(sections, index, section, indent, start, count, visited):
	if (section, start) in visited:
		print(indent + "recursion detected")

	stop = start+count
	stop = min(stop, len(section.payload))
	for i in range(start & ~3, (stop+3) & ~3, 4):

		xrefs = index.get((section.index, i), [])
		for xref in xrefs:
			print("{}# xref: {:x}:{:x}".format(indent, xref[0], xref[1]))

		def hexchar(i):
			if i >= start and i < stop:
				c = section.payload[i]
				return "{:02x}".format(c)
			else:
				return "  "

		def char(i):
			if i >= start and i < stop:
				c = section.payload[i]
				if c >= 0x20 and c < 0x80:
					return chr(c)
				else:
					return "."
			else:
				return "  "

		hexchars = hexchar(i+3) + hexchar(i+2) + hexchar(i+1) + hexchar(i)
		print("{}{:04x}: {}".format(indent, i, hexchars), end=" ")

		ref = section.fixupinfo.get(i, None)
		if ref:
			kind, target, offset = ref
			if isinstance(target, tuple):
				print("-> ({}:{:x})".format(target, offset))
			else:
				print("-> ({}:{:x})".format(target, offset))
				dump32_internal(sections, index, sections[target], indent + "  ", offset, 16, visited)
		else:
			chars = char(i) + char(i+1) + char(i+2) + char(i+3)
			print(chars)
	print()

def dump32(sections, index, section):
	visited = set()
	dump32_internal(sections, index, section, "", 0, len(section.payload), visited)

def main():
	basepath = "./pc-w"
	db = drm.DB(basepath)

	fname = sys.argv[1]
	fname = os.path.relpath(fname, basepath)
	sections, rootsectionindex = db.load(fname)

	index = build_ref_index(sections)

	for i, section in enumerate(sections):
		oneline_summary(fname, sections, i, section)
		#print_references(i, section)
		#dump32(sections, index, section)

if __name__ == '__main__':
	main()
