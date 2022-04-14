import struct, zlib, os, os.path, hashlib

class Section:
	# self.s_id
	# self.typeid
	# self.subtypeid
	# self.language
	# self.fixup
	# self.payload
	pass

class MissingReference:
	def __init__(self, key):
		self.key = key

	def get_id(self):
		assert isinstance(self.key, tuple)
		return self.key[1]

class Reference:
	def __init__(self, sections, section, offset=0):
		assert isinstance(section, Section)
		assert isinstance(offset, int)
		self.sections = sections
		self.section = section
		self.offset = offset

	def get_id(self):
		return self.section.s_id

	def __eq__(self, other):
		return isinstance(other, Reference) and \
			self.section == other.section and \
			self.offset == other.offset

	def __hash__(self):
		return hash((self.section, self.offset))

	def __str__(self):
		return "#{:04x}:{:x}".format(self.section.s_id, self.offset)

	def __repr__(self):
		return "<Reference #{:04x} : {:x}>".format(self.section.s_id, self.offset)

	def add(self, offset=0):
		return Reference(self.sections, self.section, self.offset + offset)

	def deref(self, offset=0):
		offset += self.offset
		reloc = self.section.fixupinfo.get(offset, None)
		if reloc is None:
			return None

		if isinstance(self.sections, list):
			if isinstance(reloc[1], tuple):
				return MissingReference(reloc[1])
			sections = self.sections
			section = self.sections[reloc[1]]
		else:
			section = self.sections.get(reloc[1])
			if section is None:
				return MissingReference(reloc[1])
			sections, section = section

		return Reference(sections, section, reloc[2])


	def access(self, unpack_from, offset=0):
		return unpack_from(self.section.payload, self.offset + offset)

	def access_null_terminated(self, offset=0):
		try:
			zero = self.section.payload.index(b"\x00", self.offset + offset)
		except ValueError:
			zero = None
		return self.section.payload[self.offset + offset:zero]

	def valid(self):
		return self.offset < len(self.section.payload)

import pickle


class DBSections:
	def __init__(self, db, drm_id):
		self.db = db
		self.drm_id = drm_id

	def __getitem__(self, i):
		return self.get(i)[1]

	def get(self, i):
		if isinstance(i, tuple):
			typeid, s_id = i
			if (typeid, s_id) not in self.db.index:
				return None
			drm_id, section_index = self.db.index[typeid, s_id]
			assert isinstance(section_index, int)
		else:
			drm_id, section_index = self.drm_id, i
			assert isinstance(section_index, int)

		section = self.db.load_single(drm_id, section_index)
		return DBSections(self.db, drm_id), section

class DB:
	def __init__(self, basepath_or_bigfile):
		if isinstance(basepath_or_bigfile, BigFile):
			self.basepath = None
			self.bigfile = basepath_or_bigfile
		else:
			self.basepath = basepath_or_bigfile
			self.bigfile = None
		self.index = {} # {(type, id): {(drm_id, section)}}
		self.cache = {} # {(drm_id, section_index): section}
		self.lru = [] # [(drm_id, num_sections)]

	def lookup(self, typeid, s_id):
		if (typeid, s_id) not in self.index:
			return None

		drm_id, section_index = self.index[typeid, s_id]
		sections, _ = self.load(drm_id)
		return Reference(DBSections(self, drm_id), sections[section_index])

	#def create_index(self, indexpath, fnames):
	#	index = []
	#	for fname in fnames:
	#		print(fname)
	#		with open(os.path.join(self.basepath, fname), "rb") as f:
	#			data = f.read()
	#
	#		if data[0:4] == b"CDRM":
	#			data = drm.cdrm(data)
	#		data = read(data)
	#		if not data: continue
	#		sections, root = data
	#
	#		sectioninfo = []
	#		for sec in sections:
	#			p = sec.payload
	#			sectioninfo.append((hash(p), len(p), sec.fixup, p if len(p) < 1000 else None))
	#
	#		index.append((fname, sectioninfo))
	#
	#	with open(indexpath, "wb") as f:
	#		pickle.dump(y, f)

	#def read_index(self, indexpath):
	#	with open(indexpath, "rb") as f:
	#		index = pickle.load(f)
	#
	#	self.index2 = index

	def clean_cache(self):

		# caching system isn't done yet, so don't evict anything yet
		# (this means that your python process will keep using more and more memory)
		return

		if len(self.lru) > 10:
			evict, root, num = self.lru.pop(0)
			for i in range(num):
				if (evict, i) in self.cache:
					s = self.cache[evict, i]
					if len(s.payload) > 1000 and s.typeid != 8:
						del self.cache[evict, i]

	def load_single(self, path, section_index):
		assert isinstance(section_index, int)
		drm_id = path

		if (drm_id, section_index) in self.cache:
			for i, (l_drm_id, l_root, l_num) in enumerate(self.lru):
				if drm_id == l_drm_id:
					self.lru.extend(self.lru[i:i+1])
					del self.lru[i:i+1]
					break
			return self.cache[drm_id, section_index]

		sections, root = self.load_internal(path)
		s = sections[section_index]
		assert False
		return s

	def load(self, path):
		drm_id = path
		sections, root_section = self.load_internal(path)
		return DBSections(self, drm_id), root_section

	def load_raw(self, path):
		if self.basepath:
			with open(os.path.join(self.basepath, path), "rb") as f:
				return f.read()
		if self.bigfile:
			return self.bigfile.get(path, 0xBFFF0001, 0xBFFF0001)

	def load_internal(self, path):
		drm_id = path

		for i, (l_drm_id, l_root, l_num) in enumerate(self.lru):
			if drm_id == l_drm_id:
				self.lru.extend(self.lru[i:i+1])
				del self.lru[i:i+1]
				return [
					self.cache[drm_id, i] for i in range(l_num)
				], l_root

		data = self.load_raw(path)
		if data[0:4] == b"CDRM":
			data = cdrm(data)

		sections, root = read(data)

		for i, section in enumerate(sections):
			self.index[section.typeid, section.s_id] = drm_id, i
			self.cache[drm_id, i] = section

		self.clean_cache()

		self.lru.append((drm_id, root, len(sections)))

		return sections, root


def align16(v): return (v+15)&~15

def cdrm(data):
	magic, version, count, padding = struct.unpack("<IIII", data[:16])
	if magic != 0x4D524443:
		return data

	c = 16 + count*8
	c = align16(c)

	outparts = []

	for u, (info, packed_size) in enumerate(struct.iter_unpack("<II", data[16:16+8*count])):
		unpacked_size = info >> 8
		dtype = info & 255

		d = data[c:c+packed_size]

		if dtype == 1:
			pass

		elif dtype == 2:
			d = zlib.decompress(d)

		else:
			assert False

		assert len(d) == unpacked_size
		padding = ((16-len(d))&0xf)
		outparts.append(d)
		outparts.append(b"\0" * padding)
		c += (packed_size + 0xf) & ~0xf
		#print(100*u//count, "%")

	return b"".join(outparts)


def read(data):
	version, drm_dependency_list_size, obj_dependency_list_size, unknown0C, \
	unknown10, flags, section_count, root_section = struct.unpack("<IIIIIIII", data[:32])

	if version not in (19, 21):
		return None, None

	realign = flags & 1 # TODO
	cursor = 32 + section_count*20
	obj_dependency_list = data[cursor:cursor + obj_dependency_list_size]
	cursor = 32 + section_count*20 + obj_dependency_list_size
	drm_dependency_list = data[cursor:cursor + drm_dependency_list_size]
	cursor = 32 + section_count*20 + obj_dependency_list_size + drm_dependency_list_size
	cursor = (cursor+15) & ~15

	ty_id_to_index = {}

	for i, (payloadSize, typeid, unknown05, unknown06, reloc_size_and_flags, s_id, language) in \
		enumerate(struct.iter_unpack("<IBBHIII", data[32:32+section_count*20])):
		if language & 0xc0000000 == 0x40000000: # don't pick dx9 sections
			continue
		ty_id_to_index[typeid, s_id] = i

	sections = []

	for i, (payloadSize, typeid, unknown05, unknown06, reloc_size_and_flags, s_id, language) in \
		enumerate(struct.iter_unpack("<IBBHIII", data[32:32+section_count*20])):

		sec = Section()
		sec.s_id = s_id
		sec.index = i
		sec.typeid = typeid
		sec.subtypeid = (reloc_size_and_flags >> 1) & 0x7f
		sec.language = language
		sec.unk5 = unknown05
		sec.unk6 = unknown06
		reloc_size = reloc_size_and_flags >> 8

		sec.fixup = data[cursor:cursor+reloc_size]
		cursor += reloc_size
		cursor = align16(cursor)

		sec.payload = data[cursor:cursor+payloadSize]
		cursor += payloadSize
		cursor = align16(cursor)

		sec.fixupinfo = read_reloc(sec.fixup, ty_id_to_index, len(sections), sec.payload)

		sections.append(sec) #, unknown05, unknown06, reloc_size_and_flags & 0xff])

	return sections, root_section


def read_reloc(data, ty_id_to_index, current_section_index, current_section_payload):
	if len(data) == 0:
		return {}

	relocs = {}
	f0, f1, f2, f3, f4 = struct.unpack("<IIIII", data[:20])
	c = 20
	for value in struct.iter_unpack("<Q", data[c:c+8*f0]):
		value = value[0]
		patchsite = (value & 0x00000000FFFFFFFF) >> 00
		targetoff = (value & 0xFFFFFFFF00000000) >> 32
		relocs[patchsite] = (0, current_section_index, targetoff)
		c+=8

	for value in struct.iter_unpack("<Q", data[c:c+8*f1]):
		value = value[0]
		targetidx = (value & 0x0000000000003FFF) >> 00
		patchsite = (value & 0x0000003FFFFFC000) >> 12
		targetoff = (value & 0xFFFFFFC000000000) >> 38
		relocs[patchsite] = (1, targetidx, targetoff)
		c+=8

	for value in struct.iter_unpack("<I", data[c:c+4*f2]):
		value = value[0]
		patchsite = (value & 0x01FFFFFF)*4
		targetty = value >> 25
		targetid = struct.unpack("<I", current_section_payload[patchsite:patchsite+4])[0]
		key = (targetty, targetid)
		if key in ty_id_to_index:
			relocs[patchsite] = (2, ty_id_to_index[key], 0)
		else:
			relocs[patchsite] = (2, key, 0)
		c+=4

	# wasn't there some difference between type 2 and 4
	for value in struct.iter_unpack("<I", data[c:c+4*f4]):
		value = value[0]
		patchsite = (value & 0x01FFFFFF)*4
		targetty = value >> 25
		targetid = struct.unpack("<I", current_section_payload[patchsite:patchsite+4])[0]
		key = (targetty, targetid)
		if key in ty_id_to_index:
			relocs[patchsite] = (4, ty_id_to_index[key], 0)
		else:
			relocs[patchsite] = (4, key, 0)
		c+=4

	return relocs


from zlib import crc32

flipbyte = bytes([
	0x00, 0x80, 0x40, 0xC0, 0x20, 0xA0, 0x60, 0xE0, 0x10, 0x90, 0x50, 0xD0, 0x30, 0xB0, 0x70, 0xF0,
	0x08, 0x88, 0x48, 0xC8, 0x28, 0xA8, 0x68, 0xE8, 0x18, 0x98, 0x58, 0xD8, 0x38, 0xB8, 0x78, 0xF8,
	0x04, 0x84, 0x44, 0xC4, 0x24, 0xA4, 0x64, 0xE4, 0x14, 0x94, 0x54, 0xD4, 0x34, 0xB4, 0x74, 0xF4,
	0x0C, 0x8C, 0x4C, 0xCC, 0x2C, 0xAC, 0x6C, 0xEC, 0x1C, 0x9C, 0x5C, 0xDC, 0x3C, 0xBC, 0x7C, 0xFC,
	0x02, 0x82, 0x42, 0xC2, 0x22, 0xA2, 0x62, 0xE2, 0x12, 0x92, 0x52, 0xD2, 0x32, 0xB2, 0x72, 0xF2,
	0x0A, 0x8A, 0x4A, 0xCA, 0x2A, 0xAA, 0x6A, 0xEA, 0x1A, 0x9A, 0x5A, 0xDA, 0x3A, 0xBA, 0x7A, 0xFA,
	0x06, 0x86, 0x46, 0xC6, 0x26, 0xA6, 0x66, 0xE6, 0x16, 0x96, 0x56, 0xD6, 0x36, 0xB6, 0x76, 0xF6,
	0x0E, 0x8E, 0x4E, 0xCE, 0x2E, 0xAE, 0x6E, 0xEE, 0x1E, 0x9E, 0x5E, 0xDE, 0x3E, 0xBE, 0x7E, 0xFE,
	0x01, 0x81, 0x41, 0xC1, 0x21, 0xA1, 0x61, 0xE1, 0x11, 0x91, 0x51, 0xD1, 0x31, 0xB1, 0x71, 0xF1,
	0x09, 0x89, 0x49, 0xC9, 0x29, 0xA9, 0x69, 0xE9, 0x19, 0x99, 0x59, 0xD9, 0x39, 0xB9, 0x79, 0xF9,
	0x05, 0x85, 0x45, 0xC5, 0x25, 0xA5, 0x65, 0xE5, 0x15, 0x95, 0x55, 0xD5, 0x35, 0xB5, 0x75, 0xF5,
	0x0D, 0x8D, 0x4D, 0xCD, 0x2D, 0xAD, 0x6D, 0xED, 0x1D, 0x9D, 0x5D, 0xDD, 0x3D, 0xBD, 0x7D, 0xFD,
	0x03, 0x83, 0x43, 0xC3, 0x23, 0xA3, 0x63, 0xE3, 0x13, 0x93, 0x53, 0xD3, 0x33, 0xB3, 0x73, 0xF3,
	0x0B, 0x8B, 0x4B, 0xCB, 0x2B, 0xAB, 0x6B, 0xEB, 0x1B, 0x9B, 0x5B, 0xDB, 0x3B, 0xBB, 0x7B, 0xFB,
	0x07, 0x87, 0x47, 0xC7, 0x27, 0xA7, 0x67, 0xE7, 0x17, 0x97, 0x57, 0xD7, 0x37, 0xB7, 0x77, 0xF7,
	0x0F, 0x8F, 0x4F, 0xCF, 0x2F, 0xAF, 0x6F, 0xEF, 0x1F, 0x9F, 0x5F, 0xDF, 0x3F, 0xBF, 0x7F, 0xFF
])

def flipword(w):
	return (
		(flipbyte[(w>>24)&0xff]    ) |
		(flipbyte[(w>>16)&0xff]<< 8) |
		(flipbyte[(w>> 8)&0xff]<<16) |
		(flipbyte[(w    )&0xff]<<24))

def crc32r(d):
	return flipword(crc32(bytes(flipbyte[v] for v in d)))

uint32 = struct.Struct("<L").unpack_from
uint32x4 = struct.Struct("<LLLL").unpack_from

class BigFile:
	def __init__(self, path):
		self.path = path
		self.index = self.read_index()
		self.files = []
		path = path[:-3]
		for i in range(1000):
			n = "{}{:03d}".format(path, i)
			try:
				f = open(n, "rb")
			except:
				break
			print("opened", n)
			self.files.append(f)

	def read_index(self):

		self.entries = {}

		with open(self.path, "rb") as f:
			f.seek(68)
			count = uint32(f.read(4))[0]
			hashes_b = f.read(count * 4)
			entries_b = f.read(count * 16)
			for i in range(count):
				file_hash, = uint32(hashes_b, 4*i)
				file_size, file_offset, file_language, zero = uint32x4(entries_b, 16*i)
				assert zero == 0
				self.entries.setdefault(file_hash, []).append((file_offset * 2048, file_size, file_language))

	def get_slice(self, offset, size):
		filenr = offset // 0x7FF00000
		f = self.files[filenr]
		f.seek(offset % 0x7FF00000)
		return f.read(size)

	def get(self, path, language_mask, language_ref):
		file_hash = crc32r(path)
		for offset, size, language in self.entries.get(file_hash, []):
			if language & language_mask == language_ref:
				return self.get_slice(offset, size)
