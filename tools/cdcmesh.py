bl_info = {
	"name": "CDC Mesh Importer",
	"description": "Supports drm files, collision meshes (as *.mesh/*.mesh.i file-pair; one contains vertices, the other one indices) and render meshes (from the 'Mesh' header on; might require some unpacking).",
	"author": "rrika",
	"version": (1, 0),
	"blender": (2, 80, 0), # could be lower?
	"location": "File > Import > CDC Mesh (.drm)",
	"warning": "", # used for warning icon and text in addons panel
	"category": "Import-Export"}

import bpy, bmesh
from bpy.props import *
from bpy_extras.io_utils import ImportHelper

import os.path
import array, struct, math, tempfile

import drm
from dds import convert_pcd9

# bit reversed crc32 of the name
vertex_attributes = {
	0xd2f7d823: "Position",
	0x36f5e414: "Normal",
	0x097879bd: "TesselationNormal",
	0xf1ed11c3: "Tangent",
	0x64a86f01: "Binormal",
	0x09b1d4ea: "PackedNTB",
	0x48e691c0: "SkinWeights",
	0x5156d8d3: "SkinIndices",
	0x7e7dd623: "Color1",
	0x733ef0fa: "Color2",
	0x8317902a: "TexCoord1",
	0x8e54b6f3: "TexCoord2",
	0x8a95ab44: "TexCoord3",
	0x94d2fb41: "TexCoord4",

	0x3e7f6149: "unknown"
}

def setup_mesh(mesh, indices, flatvertices=None, flatnormals=None,
	texcoords_layers=[], color_layers={}, poly_mats=None):

	mesh.vertices.add(len(flatvertices)//3)
	mesh.vertices.foreach_set('co', flatvertices)
	if flatnormals:
		assert len(flatvertices) == len(flatnormals)
		mesh.vertices.foreach_set('normal', flatnormals)

	edge_cache = {}
	edges = []
	loopv = []
	loope = []
	polys = []

	def mkedge(e):
		if e[1] < e[0]:
			e = e[1], e[0]
		try:
			return edge_cache[e]
		except:
			i = len(edge_cache)
			edge_cache[e] = i
			edges.extend(e)
			return i

	# blender can't have some faces be visible from both sides and others not
	ii = set()
	indices2 = []
	poly_mats = poly_mats or ([0]*len(indices))
	poly_mats2 = []
	for s, pm in zip(indices, poly_mats):
		s2 = frozenset(s)
		if len(s2) < 3: continue # remove degenerate faces, they mess up indexing when blender removes them
		if s2 in ii: continue
		indices2.append(s)
		poly_mats2.append(pm)
		ii.add(s2)
	indices = indices2
	poly_mats = poly_mats2

	for a, b, c in indices:
		e = mkedge((a, b))
		f = mkedge((b, c))
		g = mkedge((c, a))

		l = len(loopv)

		loopv.extend([a, b, c])
		loope.extend([e, f, g])
		polys.append(l)

	#print("len(edge_cache) =", len(edge_cache))
	#print("len(loopv) =", len(loopv))
	#print("len(polys) =", len(polys))
	mesh.edges.add(len(edge_cache))
	mesh.loops.add(len(loopv))
	mesh.polygons.add(len(polys))

	mesh.edges.foreach_set('vertices', edges)
	mesh.loops.foreach_set('vertex_index', loopv)
	mesh.loops.foreach_set('edge_index', loope)
	mesh.polygons.foreach_set('loop_start', polys)
	mesh.polygons.foreach_set('loop_total', [3]*len(polys))
	mesh.polygons.foreach_set('material_index', poly_mats)

	#for name, color_layer in color_layers.items():
	#	colors = []
	#	for vi in loopv:
	#		value = color_layer[vi]
	#		colors.extend((value, value, value))
	#	bcolors = mesh.vertex_colors.new(name=name)
	#	if not bcolors:
	#		print("couldn't add color channel", name, len(mesh.vertex_colors))
	#		continue
	#	bcolors.data.foreach_set("color", colors)

	mesh.validate(verbose=True)

	def adapt(uv):
		u, v = uv
		return 16*u, 16*v

	for layer_name, texcoords in texcoords_layers:
		mesh.uv_layers.new(name=layer_name)

	if True:
		bm = bmesh.new()
		bm.from_mesh(mesh)

		for li, (_, texcoords) in enumerate(texcoords_layers):
			uv_layer = bm.loops.layers.uv[li]
			if hasattr(bm.faces, "ensure_lookup_table"):
				bm.faces.ensure_lookup_table()
			#commented out because crashing atm
			assert len(indices) == len(bm.faces), (len(indices), len(bm.faces))
			for fi, tri in enumerate(indices):
				face = bm.faces[fi]
				for vi, z in enumerate(tri):
					face.loops[vi][uv_layer].uv = adapt(texcoords[z])

		bm.to_mesh(mesh)


def read_collisionmesh(context, basename, vertexdata, indices, instanciate):

	flatvertices = array.array("f", vertexdata)
	ic = list(struct.iter_unpack("<HHHBBHH", indices))

	mesh = bpy.data.meshes.new(basename)
	if instanciate:
		mobj = bpy.data.objects.new(basename, mesh)
		context.scene.collection.objects.link(mobj)

	setup_mesh(mesh, [c[0:3] for c in ic], flatvertices)

	return mesh

uint32 = struct.Struct("<I").unpack_from
uint16 = struct.Struct("<H").unpack_from
uint8  = struct.Struct("<B").unpack_from
vec4   = struct.Struct("<ffff").unpack_from
vec3   = struct.Struct("<fff").unpack_from
vec2f  = struct.Struct("<fff").unpack_from
vec1f  = struct.Struct("<f").unpack_from

vec2h  = struct.Struct("<hh").unpack_from
vec1h  = struct.Struct("<h").unpack_from

vec3b  = struct.Struct("<BBB").unpack_from

def read_attrib(data, base, iStride, nVertices, attr_layout):
	offset, fmt = attr_layout

	if fmt == 2: # float3
		values = [vec3(data, base + j*iStride + offset) for j in range(nVertices)]
		return values, 3

	if fmt in (4, 5, 6): # uchar3 unorm
		values = []
		for j in range(nVertices):
			x, y, z = vec3b(data, base + j*iStride + offset)
			values.append((x/255.0, y/255.0, z/255.0))
		return values, 3

	if fmt == 7: # uchar3 unorm according to what the game tells directx, but treat it as uint (it's used for skinning indices)
		values = []
		for j in range(nVertices):
			x, y, z = vec3b(data, base + j*iStride + offset)
			values.append((x, y, z))
		return values, 3

	if fmt == 19: # short2 snorm
		values = []
		for j in range(nVertices):
			x, y = vec2h(data, base + j*iStride + offset)
			values.append(((x+0.5)/32767.5, (y+0.5)/32767.5))
		return values, 2

	assert False, "unknown format {0}=0x{0:x}".format(fmt)

def read_rendermodel(context, basename, data, instanciate, armature_object=None):

	nIndices    = uint32(data, 0x0C)[0]
	iVsSelect   = uint32(data, 0x4C)[0]
	oPrimGroups = uint32(data, 0x54)[0] # PrimGroup
	oBatches    = uint32(data, 0x58)[0] # ModelBatch
	oIndices    = uint32(data, 0x60)[0]
	nSubmeshes  = uint16(data, 0x64)[0]
	nBatches    = uint16(data, 0x66)[0]

	print("read_rendermodel(..., {!r}, ...)".format(basename))
	print("    nIndices = {0} = 0x{0:x}".format(nIndices))
	print("    iVsSelect = {0} = 0x{0:x}".format(iVsSelect))
	print("    oPrimGroups = {0} = 0x{0:x}".format(oPrimGroups))
	print("    oBatches = {0} = 0x{0:x}".format(oBatches))
	print("    oIndices = {0} = 0x{0:x}".format(oIndices))
	print()

	indices = array.array("H", data[oIndices:oIndices + nIndices*2])

	out = []

	submeshIndex = 0
	for i in range(nBatches):
		name = "{}_{}".format(basename, i)

		oBatch = oBatches + i*0x60
		fDistances = vec4(data, oBatch + 0)
		nLocalSubmeshes = uint32(data, oBatch + 0x30)[0]
		nBones     = uint16(data, oBatch + 0x34)[0]
		oBoneIdxs  = uint32(data, oBatch + 0x38)[0] # matrix gather offsets
		oVertices  = uint32(data, oBatch + 0x3C)[0]
		oFormat    = uint32(data, oBatch + 0x4C)[0]
		nVertices  = uint32(data, oBatch + 0x50)[0]
		iIndex     = uint32(data, oBatch + 0x54)[0]
		nTriangles = uint32(data, oBatch + 0x58)[0]

		nAttr      = uint16(data, oFormat + 0x8)[0]
		iStride    = uint8(data, oFormat + 0xA)[0]

		if fDistances[0] > 0.0:
			# not LOD 0
			submeshIndex += nLocalSubmeshes
			continue

		poly_mats = []

		print("        ModelBatch #{}".format(i))
		print("            fDistances = {}".format(fDistances))
		print("            nVertices = {0} = 0x{0:x}".format(nVertices))
		print("            iIndex = {0} = 0x{0:x}".format(iIndex))
		print("            nTriangles = {0} = 0x{0:x}".format(nTriangles))
		print("            iStride = {0} = 0x{0:x}".format(iStride))
		print()

		layout = {}

		for j in range(nAttr):
			oAttr = oFormat + 0x10 + 8 * j
			iAttrHash = uint32(data, oAttr)[0]
			iAttrLoc = uint16(data, oAttr+4)[0]
			iAttrFmt = uint8(data, oAttr+6)[0]
			print("          Attribute #{} {:08x} {} {:08x} format={}".format(j, iAttrHash, vertex_attributes.get(iAttrHash, ""), iAttrLoc, iAttrFmt))
			if iAttrHash in vertex_attributes:
				layout[vertex_attributes[iAttrHash]] = (iAttrLoc, iAttrFmt)

		for j in range(nLocalSubmeshes):
			oPrimGroup = oPrimGroups + 0x40 * submeshIndex
			iStartIndex = uint32(data, oPrimGroup + 0x10)[0]
			nTrianglesSub = uint32(data, oPrimGroup + 0x14)[0]
			iGroupFlags = uint32(data, oPrimGroup + 0x1C)[0]
			iMaterial   = uint32(data, oPrimGroup + 0x28)[0]
			print("          PrimGroup #{} (#{})".format(j, submeshIndex))
			print("              iStartIndex = {0} = 0x{0:x}".format(iStartIndex))
			print("              nTrianglesSub = {0} = 0x{0:x}".format(nTrianglesSub))
			print("              iMaterial = {0} = 0x{0:x}".format(iMaterial))
			print("              indices = {0}..{1} = 0x{0:x}..0x{1:x}".format(
				iStartIndex, iStartIndex + nTrianglesSub * 3))
			print()
			poly_mats += [iMaterial] * nTrianglesSub
			submeshIndex += 1

		lIndices   = indices[iIndex:iIndex + nTriangles*3]
		#lVertices  = [vec3(data, oVertices + j*iStride + 0x00) for j in range(nVertices)]
		#lNormals   = [vec3(data, oVertices + j*iStride + 0x10) for j in range(nVertices)]
		#lTexCoords0C = [vec2h(data, oVertices + j*iStride + 0x0C) for j in range(nVertices)]
		#lTexCoords1C = [vec2h(data, oVertices + j*iStride + 0x1C) for j in range(nVertices)]
		#lTexCoords20 = [vec2h(data, oVertices + j*iStride + 0x20) for j in range(nVertices)]
		#lTexCoords24 = [vec2h(data, oVertices + j*iStride + 0x24) for j in range(nVertices)]
		if "SkinWeights" in layout and "SkinIndices" in layout:
			lSkinWeights, dimSkinWeights = read_attrib(data, oVertices, iStride, nVertices, layout["SkinWeights"])
			lSkinIndices, dimSkinIndices = read_attrib(data, oVertices, iStride, nVertices, layout["SkinIndices"])
		else:
			lSkinWeights = [(255, 0, 0)] * nVertices
			lSkinIndices = [(0, 0, 0)] * nVertices

		lVertices, dimVertices = read_attrib(data, oVertices, iStride, nVertices, layout["Position"])
		lNormals,  dimNormals  = read_attrib(data, oVertices, iStride, nVertices, layout["Normal"])
		assert dimVertices == 3
		assert dimNormals == 3

		normals = []
		for (x, y, z) in lNormals:
			x = x * 2 - 1
			y = y * 2 - 1
			z = z * 2 - 1
			l = math.sqrt(x*x + y*y + z*z)
			x = x/l
			y = y/l
			z = z/l
			normals.append((x, y, z))

		# uvmaps = [#("lTexCoords0C", lTexCoords0C),
		# 	 ("lTexCoords1C", lTexCoords1C),
		# 	 ("lTexCoords20", lTexCoords20),
		# 	 ("lTexCoords24", lTexCoords24)
		# ]

		uvmaps = []
		for uvmap in ("TexCoord1", "TexCoord2", "TexCoord3", "TexCoord4"):
			if uvmap in layout:
				uvValues, dimUv = read_attrib(data, oVertices, iStride, nVertices, layout[uvmap])
				assert dimUv == 2
				uvmaps.append((uvmap, uvValues))

		colors = {}
		for color in ("Color1", "Color2"):
			if color in layout:
				lAttr = [vec1f(data, oVertices + j*iStride + layout[color][0] + 0)[0] for j in range(nVertices)]
				colors[color] = lAttr

		# for k in range(0x18, iStride, 4):
		# 	lAttrF0 = [vec1f(data, oVertices + j*iStride + k + 0)[0] for j in range(nVertices)]
		# 	#lAttrH0 = [vec1h(data, oVertices + j*iStride + k + 0)[0] / 0xffff for j in range(nVertices)]
		# 	#lAttrH2 = [vec1h(data, oVertices + j*iStride + k + 2)[0] / 0xffff for j in range(nVertices)]
		# 	colors["lAttrFloat{:X}".format(k+0)] = lAttrF0
		# 	#colors["lAttrShort{:X}".format(k+0)] = lAttrH0
		# 	#colors["lAttrShort{:X}".format(k+2)] = lAttrH2

		mesh = bpy.data.meshes.new(name)
		if instanciate:
			mobj = bpy.data.objects.new(name, mesh)
			context.scene.collection.objects.link(mobj)

		out.append(mesh)

		setup_mesh(mesh,
			list(zip(lIndices[0::3], lIndices[1::3], lIndices[2::3])),
			[v for vertex in lVertices for v in vertex],
			[n for normal in normals for n in normal],
			uvmaps,
			colors,
			poly_mats = poly_mats
		)

		if instanciate:
			# apply vertex weights
			gs = []
			for i in range(nBones):
				bone_index = uint32(data, oBoneIdxs + 4*i)[0]
				g = mobj.vertex_groups.new(name='bone{}'.format(bone_index))
				gs.append(g)

			if armature_object:
				for i in range(nVertices):
					for j in range(3):
						w = lSkinWeights[i][j]
						x = lSkinIndices[i][j]
						if w:
							gs[x].add([i], w/255.0, 'REPLACE')

				bpy.context.view_layer.objects.active = mobj
				bpy.ops.object.modifier_add(type='ARMATURE')
				bpy.context.object.modifiers["Armature"].object = armature_object

	return out

def read_renderterrain(context, basename, data, instanciate):
	# RenderTerrainDataHeader
	nLists   = uint32(data, 0x08)[0]
	oTargets = uint32(data, 0x0C)[0]
	nTargets = uint32(data, 0x10)[0]
	oFormatStream = uint32(data, 0x14)[0]
	nFormats = uint16(data, 0x18)[0]
	oBuffers = uint32(data, 0x20)[0]
	nBuffers = uint16(data, 0x24)[0]
	oLists   = uint32(data, 0x28)[0]
	oIndices = uint32(data, 0x34)[0]
	nIndices = uint32(data, 0x38)[0]

	nMeshes = 1

	indices = array.array("H", data[oIndices:oIndices + nIndices*2])

	oFormats = []
	for i in range(nFormats):
		nAttr = uint16(data, oFormatStream + 0x8)[0]
		iStride = uint16(data, oFormatStream + 0xA)[0]
		oFormatStream += 0x10
		oFormats.append((iStride, [struct.Struct("<LHH").unpack_from(data, oFormatStream + j*8) for j in range(nAttr)]))
		oFormatStream += nAttr * 8
		del nAttr

	del oFormatStream

	lBuffers = []

	for i in range(nBuffers):
		oBuffer    = oBuffers + i*0x10
		oVertices  = uint32(data, oBuffer + 0x0)[0]
		nVertices  = uint32(data, oBuffer + 0x8)[0]
		iFormat    = uint32(data, oBuffer + 0xC)[0]

		iStride, oFormat = oFormats[iFormat]

		for attr, a, b in oFormat:
			print(a, b, "verts?!" if attr == 0xD2F7D823 else "...")

		lVertices  = [
			(vec3(data, oVertices + j*iStride + 0x00),
			 vec2h(data, oVertices + j*iStride + 0x0C))
			for j in range(nVertices)]
		lBuffers.append(lVertices)

	out = []

	for i in range(nLists):
		oList   = uint32(data, oLists + i*4)[0]
		if oList == 0 or oList >= len(data)-2: continue
		# TerrainChunkArray
		nRanges = uint16(data, oList)[0]
		print("nranges:", nRanges)

		for j in range(nRanges):
			oRange = oList+4+16*j
			# TerrainChunk
			target     = uint16(data, oRange + 0x0)[0]
			count      = uint16(data, oRange + 0x2)[0]
			firstIndex = uint32(data, oRange + 0x4)[0]

			print("{:x}/{:x} {:x} @ {:x} = {:x} + {:x}".format(i, j, target, oRange, oList, oRange-oList))
			# RenderTerrainGroup
			materialIndex = uint32(data, oTargets + target*0x20 + 0)[0]
			bufferIndex = uint32(data, oTargets + target*0x20 + 4)[0]
			groupFlags = uint32(data, oTargets + target*0x20 + 8)[0]

			if bufferIndex not in range(len(lBuffers)):
				print(i,j,"had invalid bufferIndex", bufferIndex)
				continue
			lVertices = lBuffers[bufferIndex]
			lIndices = indices[firstIndex:firstIndex+count]

			if True:
				min_index = min(lIndices)
				max_index = max(lIndices)
				lVertices = lVertices[min_index:max_index+1]
				lIndices = [i-min_index for i in lIndices]

			name = "{}_{}_{}".format(basename, i, j)
			mesh = bpy.data.meshes.new(name)
			out.append(mesh)
			if instanciate:
				mobj = bpy.data.objects.new(name, mesh)
				context.scene.collection.objects.link(mobj)

			flattened_xyz = [n for vertex, uvs in lVertices for n in vertex]
			uvs = [uv for vertex, uv in lVertices]

			setup_mesh(mesh,
				list(zip(lIndices[0::3], lIndices[1::3], lIndices[2::3])),
				flattened_xyz,
				texcoords_layers=[["offset12", uvs]],
				poly_mats=[materialIndex]*(len(lIndices)//3)
			)

	return out

def setup_skeleton(name, relbones):
	armature = bpy.data.armatures.new(name)
	armature_object = bpy.data.objects.new(name, armature)
	bpy.context.collection.objects.link(armature_object)
	armature_object.select_set(state = True, view_layer = bpy.context.view_layer)
	bpy.context.view_layer.objects.active = armature_object
	bpy.ops.object.mode_set(mode='EDIT', toggle=False)
	edit_bones = armature_object.data.edit_bones

	absbones = []
	for i, (parent, (x, y, z)) in enumerate(relbones):
		if parent is not None:
			px, py, pz = absbones[parent][1]
		else:
			px, py, pz = 0, 0, 0
		absbones.append((parent, (px + x, py + y, pz + z)))

	childpos = {}
	for i, (parent, pos) in enumerate(absbones):
		childpos.setdefault(parent, []).append(pos)

	ebones = []
	for i, (parent, (x, y, z)) in enumerate(absbones):

		b = edit_bones.new('bone{}'.format(i))
		ebones.append(b)

		if parent is not None:
			p = ebones[parent]
			b.parent = p
			px, py, pz = p.head
		else:
			px, py, pz = 0, 0, 0

		b.head = (x, y, z)
		c = childpos.get(i, [])
		if c:
			b.tail = c[0] # pick a random child to connect to
		else:
			b.tail = (x, y, z+1)

	bpy.ops.object.mode_set(mode='OBJECT')
	armature_object.select_set(state = False, view_layer = bpy.context.view_layer)
	return armature_object

def read_skeleton(skeletonblob, bonecount):
	name = "skeleton{}".format(skeletonblob)
	bones = []
	for i in range(bonecount):
		bone = skeletonblob.add(64 * i)
		xyz = bone.access(vec3, 0x20)
		parent = bone.access(uint32, 0x38)[0]
		bones.append((parent if parent != 0xffffffff else None, xyz))
	return setup_skeleton(name, bones)


# gcc -shared -o libsquish.so -Wl,--whole-archive /usr/lib/libsquish.a -Wl,--no-whole-archive -lm

# import ctypes
# if False:
# 	import os.path
# 	path = os.path.join(os.path.dirname(__file__), "libsquish.so") # a dll really
# 	libsquish = ctypes.CDLL(path)
# 	libsquish_GetStorageRequirements = getattr(libsquish, "?GetStorageRequirements@squish@@YAHHHH@Z")
# 	libsquish_DecompressImage = getattr(libsquish, "?DecompressImage@squish@@YAXPEAEHHPEBXH@Z")
# else:
# 	libsquish = ctypes.CDLL("libsquish.so")
# 	libsquish_GetStorageRequirements = getattr(libsquish, "_ZN6squish22GetStorageRequirementsEiii")
# 	libsquish_DecompressImage = getattr(libsquish, "_ZN6squish15DecompressImageEPhiiPKvi")


def read_pcd9(basename, sec_id, data):
	# todo: allow use of a user specified persistent cache
	fd, fname = tempfile.mkstemp(suffix=".dds")

	width, height, out_blob = convert_pcd9(data)
	f = os.fdopen(fd, "wb")
	f.write(out_blob)
	f.close() # blender wants to mmap the file which sometimes fails if the file is still open

	im = bpy.data.images.load(fname)
	im.name = "{}.{:x}".format(basename , sec_id)
	im.pack()

	os.unlink(fname)

	t = bpy.data.textures.new(basename, 'IMAGE')
	t.image = im

	return t

Reference = drm.Reference
uint32 = struct.Struct("<I").unpack_from
uint8  = struct.Struct("<B").unpack_from

def read_mat(basename, matref):
	print(matref)
	print(matref.section)
	print(matref.section.fixupinfo)
	print(matref.deref(0x4C + 0x4 * 0))
	print(matref.deref(0x4C + 0x4 * 1))
	print(matref.deref(0x4C + 0x4 * 2))
	print(matref.deref(0x4C + 0x4 * 3))
	print(matref.deref(0x4C + 0x4 * 4))
	print(matref.deref(0x4C + 0x4 * 5))

	# as an example, here are the submaterials for a random object:
	# submaterial 0: no pixel shader
	# submaterial 1: only concerned with alpha-testing
	# submaterial 2: empty in DX11
	# submaterial 3: material shading, sampling of lightmaps happens here
	# submaterial 4: renders black
	# submaterial 5: empty in DX11
	# submaterial 6: empty
	# submaterial 7: draw normals
	# submaterial 8: copy of submaterial 3
	# submaterial 9: empty
	# submaterial A: empty
	# submaterial B: empty
	# submaterial C: empty
	# submaterial D: empty
	# submaterial E: empty
	# submaterial F: empty

	# the most interesting submaterial is 3/8 then

	def read_submat(submatblob):
		if submatblob is None:
			return (None, None, None, None, [])

		ps = submatblob.deref(0x00)
		vs = submatblob.deref(0x04)
		hs = submatblob.deref(0x08)
		ds = submatblob.deref(0x0c)
		tx = submatblob.deref(0x18)

		r_indexA = 0
		r_byte14 = submatblob.access(uint8, 0x14)[0]
		r_countB = submatblob.access(uint8, 0x15)[0]
		r_countA = submatblob.access(uint8, 0x16)[0]
		r_indexB = submatblob.access(uint8, 0x17)[0]

		p = []
		if tx:
			for r_i in range(r_indexA, r_indexA+r_countA):
				ttx = tx.access(uint32, r_i*16)[0]
				tbind = tx.access(uint8, r_i*16+0xD)[0]
				p.append((ttx, tbind))
		return (ps, vs, hs, ds, p)

	submats = [
		read_submat(matref.deref(0x4c+4*i))
		for i in range(16)
	]

	def hash_or_repr(x):
		if x is None:
			return "null"
		if isinstance(x, drm.MissingReference):
			return "{:04x}".format(x.get_id())
		return repr(x)

	mat = bpy.data.materials.new(basename)
	mat.use_nodes = True
	tree = mat.node_tree

	ps_hash = -1 # submats[-3][0]...
	vs_hash = -1 # submats[-3][1]...
	ps_hash_primary_texture = {
		# 0x1234: 0
	}
	ps_hash_further_mappings = {
		# 0x1234: [(0, "Specular")]
	}

	def build_node_graph():

		# this node can provide a specific UV map
		# this will be necessary as different textures require different UVs
		#
		# uv = tree.nodes.new("ShaderNodeUVMap")
		# uv_output = uv.outputs["UV"]
		
		# this node makes prototyping a bit easier, as it lets users in
		# blender switch through different UV sets easily without rewriting
		# the materials
		tex_coordinate = tree.nodes.new("ShaderNodeTexCoord")
		uv_output = tex_coordinate.outputs["UV"]
		bsdf = tree.nodes['Principled BSDF']

		texs = []

		y = 0

		for i, (ps, vs, _, _, tex_ids) in enumerate(submats):
			mat["submat_{:02}".format(i)] = "ps {} vs {}".format(hash_or_repr(ps), hash_or_repr(vs))
			if not tex_ids: continue
			for j, (tex_id, binding) in enumerate(tex_ids):
				tex = tree.nodes.new("ShaderNodeTexImage")
				texs.append(tex)
				mat.node_tree.links.new(tex.inputs["Vector"], uv_output)
				tex.image = texregistry[tex_id].image
				tex.label = "submat {} tex {} id {:04x} bind {}".format(i, j, tex_id, binding)
				tex.location.x = -400
				tex.location.y = y
				tex.hide = True
				y -= 40
			y -= 40

		texmid = (y-30) / 2
		uvmid = tex_coordinate.height / 2
		tex_coordinate.location.x = -700
		tex_coordinate.location.y = texmid+uvmid

		if len(texs) > 0:
			primary_tex = ps_hash_primary_texture.get(ps_hash, len(texs)-1)
			if primary_tex >= len(texs):
				print("out of bounds spec for ps_hash_primary_texture[0x{:04x}] = {} when #texs is {}".format(ps_hash, primary_tex, len(texs)))
				primary_tex = len(texs)-1

			mat.node_tree.links.new(bsdf.inputs["Base Color"], texs[primary_tex].outputs["Color"])

		for tex, bsdf_input in ps_hash_further_mappings.get(ps_hash, []):
			mat.node_tree.links.new(bsdf.inputs[bsdf_input], texs[tex].outputs["Color"])

	runlater.append(build_node_graph)

	return mat

def read_matrefs(sec, meshes, offset):

	fixup = sec.fixupinfo.get(offset, None)
	if not fixup: return
	madd = fixup[2]

	data = sec.payload
	uint32 = struct.Struct("<I").unpack_from
	count = uint32(data, madd)[0]
	sids = [uint32(data, madd+4+4*i)[0] for i in range(count)]

	def fixmaterials():
		for mesh in meshes:
			for sid in sids:
				try:
					mesh.materials.append(matregistry[sid])
				except Exception as e:
					print(e)

	runlater.append(fixmaterials)


class CDCMeshImporter(bpy.types.Operator, ImportHelper):
	bl_idname = "import_mesh.cdcmesh"
	bl_label = 'Import CDC Mesh'

	files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)

	def execute(self, context):
		bpy.ops.object.select_all(action="DESELECT")

		directory = os.path.dirname(self.properties.filepath)
		items = [
			(entry.name, os.path.join(directory, entry.name))
			for entry in self.properties.files
		]

		execute_items(context, items)

		return {'FINISHED'}

texregistry = None
matregistry = None
runlater = None

def load_mesh(out, context, sections, sec, sname, instanciate):
	global runlater, texregistry

	if sec.typeid == 0xC:
		if sec.subtypeid == 26:
			#continue # for now
			data = sec.payload[sec.payload.find(b"Mesh"):]
			#try:

			armature_object = None
			meshheader = drm.Reference(sections, sec)
			meshC = meshheader.deref(0xC)
			meshC = None #disable for now
			if meshC:
				bonecount = meshC.access(uint32, 8)[0]
				bones = meshC.deref(0xC)
				if bones:
					armature_object = read_skeleton(bones, bonecount)

			meshes = read_rendermodel(context, sname, data, instanciate, armature_object)
			#except Exception as e:
			#	print("couldn't load", sname, e)
			#	continue
			out.extend(meshes)
			read_matrefs(sec, meshes, 0x8)


		elif sec.subtypeid == 24:
			_, data_i, data_o = sec.fixupinfo[4] # RenderTerrainData::pHeader
			data = sec.payload[data_o:]
			meshes = read_renderterrain(context, sname, data, instanciate)
			out.extend(meshes)
			read_matrefs(sec, meshes, 0xC)

	elif sec.typeid == 0x5:
		texregistry[sec.s_id] = read_pcd9(sname, sec.s_id, sec.payload)
	elif sec.typeid == 0xA and (sec.language >> 30) != 1:
		matref = Reference(sections, sec, 0)
		matregistry[sec.s_id] = read_mat(sname, matref)

def execute_items(context, items, instanciate=True):
	global runlater, texregistry, matregistry

	texregistry = {}
	matregistry = {}
	runlater = []

	out = []
	for basename, filepath in items:

		if not isinstance(filepath, str):
			# hack to sneak in pre-loaded drms
			assert isinstance(filepath, drm.Reference), repr(type(filepath))
			load_mesh(out, context, filepath.sections, filepath.section, basename, instanciate)
			continue

		try:
			with open(filepath, 'rb') as f:
				data = f.read()
		except:
			print("open failed:", filepath)
			continue

		if data[0:4] == b"CDRM":
			data = drm.cdrm(data)

		if data[0:4] == b"Mesh":
			# drm/section.rendermesh/mesh
			out.extend(read_rendermodel(context, basename, data, instanciate))

		elif data[0:4] == b"\x15\0\0\0":
			# drm
			# drmmesh_load(filepath, data)
			sections = drm.read(data)[0]
			for i, sec in enumerate(sections):
				sname = "{}.{}".format(basename, i)
				print(sname)
				load_mesh(out, context, sections, sec, sname, instanciate)

		else:
			# drm/section.collisiondata1
			# drm/section.collisiondata2
			with open(filepath+".i", 'rb') as f:
				indices = f.read()

			out.append(read_collisionmesh(context, basename, data, indices, instanciate))

	for r in runlater: r()

	return out

def menu_func_import(self, context):
	self.layout.operator(CDCMeshImporter.bl_idname, text="CDC Mesh (.drm/.cdcmesh)")

def register():
	bpy.utils.register_class(CDCMeshImporter)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
	bpy.utils.unregister_class(CDCMeshImporter)
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
	register()
