import struct, zlib, os, os.path, hashlib
import bigfile

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

	def __len__(self):
		return self.db.section_count[self.drm_id]

	def __iter__(self):
		return (self.get(i)[1] for i in range(len(self)))

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
		if isinstance(basepath_or_bigfile, bigfile.BigFile):
			self.basepath = None
			self.bigfile = basepath_or_bigfile
		else:
			self.basepath = basepath_or_bigfile
			self.bigfile = None
		self.index = {} # {(type, id): {(drm_id, section)}}
		self.cache = {} # {(drm_id, section_index): section}
		self.lru = [] # [(drm_id, num_sections)]
		self.section_count = {} # {drm_id: num_sections}

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
		self.section_count[drm_id] = len(sections)

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


def read(data, *, check=False):
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

	if check:
		data2 = write(
			obj_dependency_list,
			drm_dependency_list,
			unknown0C,
			unknown10,
			flags,
			sections,
			root_section)

		if False:
			import binascii
			print(binascii.hexlify(data).decode("ascii"))
			print(binascii.hexlify(data2).decode("ascii"))

		assert len(data) == len(data2), (len(data), len(data2))
		assert data == data2

	return sections, root_section

def pad16join(parts):
	allparts = []
	count = 0
	for part in parts:
		allparts.append(part); count += len(part)
		npad = (-count) % 16
		allparts.append(b"\0" * npad); count += npad
	return b"".join(allparts)

def write(obj_dependency_list, drm_dependency_list, unknown0C,
	unknown10, flags, sections, root_section):

	parts = []

	#obj_dependency_list = b"\0".join(obj_dependency_list)
	#drm_dependency_list = b"\0".join(drm_dependency_list)

	header = struct.pack("<IIIIIIII", 21,
		len(drm_dependency_list),
		len(obj_dependency_list),
		unknown0C, unknown10, flags, len(sections), root_section)

	for section in sections:
		header += struct.pack("<IBBHIII",
			len(section.payload),
			section.typeid, # byte
			section.unk5,   # byte
			section.unk6,   # short
			(len(section.fixup) << 8) | (section.subtypeid << 1),
			section.s_id,
			section.language)

	header += obj_dependency_list
	header += drm_dependency_list

	parts.append(header)

	for section in sections:
		parts.append(section.fixup)
		parts.append(section.payload)

	return pad16join(parts)

def read_reloc(data, ty_id_to_index, current_section_index, current_section_payload, *, check=False):
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

	if check:
		data2 = write_reloc(relocs, current_section_index)
		assert data == data2

	return relocs

def write_reloc(reloc, section_index):
	if not reloc:
		return b""

	r0 = b""
	r1 = b""
	r2 = b""
	r4 = b""
	for patchsite, (ty, target, targetoff) in reloc.items():
		if ty == 0:
			assert patchsite <= 0xffffffff
			assert targetoff <= 0xffffffff
			value = patchsite | (targetoff << 32)
			r0 += struct.pack("<Q", value)

		elif ty == 1:
			assert target <= 0x3FFF
			assert patchsite <= 0xFFFFFF
			assert targetoff <= 0x3FFFFFF
			value = target | (patchsite << 12) | (targetoff << 38)
			r1 += struct.pack("<Q", value)

		elif ty in (2, 4):
			(targetty, targetid) = target
			assert targetoff == 0
			assert patchsite % 4 == 0
			assert targetty <= 0x7F
			assert (patchsite >> 2) <= 0x01FFFFFF
			value = (patchsite >> 2) | (targetty << 25)
			if ty == 2:
				r2 += struct.pack("<I", value)
			else:
				r4 += struct.pack("<I", value)

	rawreloc = struct.pack("<IIIII",
		len(r0) // 8,
		len(r1) // 8,
		len(r2) // 4,
		0,
		len(r4) // 4)

	rawreloc += r0
	rawreloc += r1
	rawreloc += r2
	rawreloc += r4

	return rawreloc
