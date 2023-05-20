import sys, os, struct
import os.path
import drm

uint8 = struct.Struct("<B").unpack_from
uint16 = struct.Struct("<H").unpack_from
uint32 = struct.Struct("<I").unpack_from
int16 = struct.Struct("<b").unpack_from
f32 = struct.Struct("<f").unpack_from

# usage: python dump_animfragment.py pc-w/occupation_sarifidle.drm 2
# this code is very incomplete

fname = sys.argv[1]
sectionindex = int(sys.argv[2])
basepath = "./pc-w"

db = drm.DB(basepath)
fname = os.path.relpath(fname, basepath)
sections, rootsectionindex, _ = db.load(fname)

anim_fragment = drm.Reference(sections, sections[sectionindex])

framecount = anim_fragment.access(uint16, 0x32)[0]
byte36 = anim_fragment.access(uint8, 0x36)[0]

# these three move forward during decoding
masks = anim_fragment.deref(0x54)
modes = anim_fragment.deref(0x58)
values = anim_fragment.deref(0x5C)

bitcnt = lambda n: bin(n).count("1")

print("framecount = {}".format(framecount))
for i in range(byte36):
	mask = masks.access(uint16)[0]
	masks = masks.add(2)
	print("index {:2} mask {:04x} @ {:4x} / {:4x} / {:4x}".format(i, mask, masks.offset, modes.offset, values.offset))
	if framecount == 1:
		count = bitcnt(mask & 0xff)
		# modes = modes.add(2 * count)
		values = values.add(4 * count)
	else:
		for j in range(bitcnt(mask)):
			mode = modes.access(uint16)[0]
			if mode == 0:
				fmt16 = modes.access(uint16, 2)[0]
				print("  raw", "i16" if fmt16 else "f32")
				modes = modes.add(4)
				values = values.add(
					2 * ((framecount + 1)&~1) if fmt16 else 4*framecount
				)

			elif mode == 1:
				value = values.access(f32)[0]
				print("  constant @ {:4x} = {}".format(values.offset, value))
				modes = modes.add(2)
				values = values.add(4)

			elif mode == 2:
				fmt16 = modes.access(uint16, 2)[0]
				count = modes.access(uint16, 4)[0]
				print("  linear", "i16" if fmt16 else "f32", count, "keyframes")
				modes = modes.add(5 + (count|1))
				values = values.add(
					2 * ((count + 1)&~1) if fmt16 else 4*count
				)

			else:
				print(" ", mode, "?")
