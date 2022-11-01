bl_info = {
	"name": "CDC Unit Importer",
	"description": "Import CDC unit files",
	"author": "rrika",
	"version": (1, 0),
	"blender": (3, 0, 0),
	"location": "File > Import > CDC Unit (.drm)",
	"warning": "", # used for warning icon and text in addons panel
	"category": "Import-Export"}

import mathutils
import bpy
import os.path
import struct
from bpy.props import *
from bpy_extras.io_utils import ImportHelper

import drm

#def linkobject():
#	with bpy.data.libraries.load(filepath) as (data_from, data_to):
#		data_to.scenes = ["Scene"]

def collect_existing():
	c = {}
	for mesh in bpy.data.meshes:
		if hasattr(mesh, "cdcorigin") and mesh.cdcorigin:
			c.setdefault(mesh.cdcorigin, []).append(mesh)
	return c

class UnitImporter(bpy.types.Operator, ImportHelper):
	bl_idname = "import_mesh.cdcunit"
	bl_label = 'Import CDC Unit'

	files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)

	use_impostors: bpy.props.BoolProperty(
		name = "Use impostors",
		description = "Place empties instead of loading meshes.",
		default = False)

	load_obj: bpy.props.BoolProperty(
		name = "Load objects",
		description = "Load interactive objects.",
		default = True)

	load_imf: bpy.props.BoolProperty(
		name = "Load IMF",
		description = "Load non-interactive instantiated objects.",
		default = True)

	load_cell: bpy.props.BoolProperty(
		name = "Load unit objects",
		description = "Load non-interactive bespoke objects.",
		default = True)

	load_cd: bpy.props.BoolProperty(
		name = "Load collision meshes",
		description = "Load collection meshes.",
		default = False)

	load_occlusion_boxes: bpy.props.BoolProperty(
		name = "Load occlusion meshes",
		description = "Load occlusion meshes.",
		default = False)

	basepath: bpy.props.StringProperty(
		name = "DRM Root",
		description = "Path to pc-w/", 
		default = ".../unpack/pc-w")

	directory: StringProperty(subtype='DIR_PATH')

	def execute(self, context):

		basepath = self.properties.basepath

		if not os.path.exists(os.path.join(basepath, "objectlist.txt")):
			# guess the root
			for entry in self.properties.files:
				parts = os.path.split(os.path.join(self.directory, entry.name))
				while parts and parts != "/":
					path, _ = parts
					try_this = os.path.join(path, "objectlist.txt")
					if os.path.exists(try_this):
						basepath = os.path.join(path)
						break
					parts = os.path.split(path)
				break

		scene = bpy.context.scene
		db = drm.DB(basepath)

		def coll(name):
			for c in bpy.data.collections:
				# check if the found collection is in the right scene
				if c.name == name:
					return c
			c = bpy.data.collections.new(name)
			scene.collection.children.link(c)
			return c

		lod_levels = 1
		lod_collections = []
		for i in range(lod_levels):
			lod_collections.append(coll("IMF LOD Level {}".format(i)))

		non_imf_collection = coll("Non-IMF meshes")
		cd_collection = coll("Collision meshes")
		occ_collection = coll("Occlusion meshes")
		unit_mesh_collection = coll("Unit meshes")

		if self.properties.use_impostors:
			def meshes_for_i(fname):
				return [None]
				#return [("impostor", None)]
		else:
			import cdcmesh
			pt = basepath
			def meshes_for_i(fname):
				if isinstance(fname, str):
					fname = fname.replace("\\", os.path.sep)
					x = (fname, os.path.join(pt, fname))
				elif isinstance(fname, drm.Reference):
					x = ("section.{}".format(fname.get_id()), fname)
				else:
					assert False
				#try:
				return cdcmesh.execute_items(context, [x], instanciate=False)
				#except FileNotFoundError:
				#	return [None]
				#except Exception as e:
				#	print(e)
				#	return [None]

		mesh_cache = collect_existing()
		def meshes_for(fname, fun=lambda x: x):
			#print("meshes_for", fname)
			if fname in mesh_cache:
				#print("  returns", len(mesh_cache[fname]))
				return mesh_cache[fname]
			ms = meshes_for_i(fname)
			if isinstance(fname, str):
				for m in ms:
					if m:
						m.cdcorigin = fname
			ms = fun(ms)
			mesh_cache[fname] = ms
			#print("  returns", len(ms))
			return ms

		def mk_matrix(mat):
			return mathutils.Matrix([
				mat[0:13:4],
				mat[1:14:4],
				mat[2:15:4],
				mat[3:16:4]
			])

		objlist = {}
		with open(os.path.join(basepath, "objectlist.txt")) as f:
			for line in f.read().split("\n")[1:]:
				try:
					num, name = line.split(",", 1)
					objlist[int(num)] = name
				except:
					print(line)

		uint32 = struct.Struct("<I").unpack_from
		uint16 = struct.Struct("<H").unpack_from
		uint8  = struct.Struct("<B").unpack_from

		identity_mat = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)

		for entry in self.properties.files:
			filepath = os.path.join(self.directory, entry.name)

			sections, unit_i = db.load(os.path.relpath(filepath, start=basepath))
			unitref = drm.Reference(sections, sections[unit_i])

			sub0 = unitref.deref(0)
			rel = sub0.deref(0x4)
			cd0 = sub0.deref(0x18)
			rel_count = sub0.access(uint16, 0x2)[0]
			cd0_count = sub0.access(uint32, 0x14)[0]

			sub30 = unitref.deref(0x30)
			if sub30:
				obj_count  = sub30.access(uint32, 0x14)[0]
				obj2_count = sub30.access(uint32, 0x1C)[0]
				imf_count  = sub30.access(uint32, 0xA4)[0]
				obj_ = sub30.deref(0x18)
				imf = sub30.deref(0xA8)
			else:
				obj_count = 0
				obj2_count = 0
				imf_count = 0
				obj_ = None
				imf = None

			sub50 = unitref.deref(0x50)
			if sub50:
				sub50_0 = sub50.deref(0)
				sub50_14 = sub50.deref(0x14)
				sub50_18 = sub50.deref(0x18)
				if sub50_18:
					sub50_18_4 = sub50_18.deref(4)
					cell_count, cell_count_ = sub50_0.access(struct.Struct("<LL").unpack_from)
				else:
					sub50_18_4 = None
					cell_count, cell_count_ = 0, 0
			else:
				sub50_0 = None
				sub50_14 = None
				sub50_18_4 = None
				cell_count, cell_count_ = 0, 0

			print("#cell #cell", cell_count, cell_count_) # should be equal

			objs = []
			if sub50_18_4:
				objs.append((identity_mat, sub50_18_4, "cell"))

			for i in range(cell_count):
				cell = sub50_14.deref(4*i)
				cellsub0 = cell.deref(0)
				print("{} + 0 => {}".format(cell, cellsub0))
				print("{} + 4 =>".format(cell), end=" ")
				try:
					cellsub4 = cell.deref(0x4)
					print("{} =>".format(cellsub4), end=" ")
					cellsub4_0 = cellsub4.deref(0x0)
					print("{}".format(cellsub4_0))
				except Exception as e:
					cellsub4_0 = None
					print("error", e)

				cellsub20 = cell.deref(0x20)
				cellname = cellsub0.deref(0x0)

				# this seems wrong
				floats = cellsub0.access(struct.Struct("<ffffffff").unpack_from)

				try:
					cellname = cellname.access_null_terminated().decode("ascii")
				except:
					cellname = "unknown cell {}".format(i)
				print("  ", cellname, floats, cellsub4_0)

				if self.properties.load_cell and cellsub4_0 is not None:
					objs.append((identity_mat, cellsub4_0, "cell"))

				if self.properties.load_occlusion_boxes: # just the portal box
					objs.append((identity_mat, cellsub20, "occlusion"))

			print("#obj #imf", obj_count, imf_count)

			if not self.properties.load_obj:
				obj_count = 0 # cant reconstruct transform correctly yet
			if not self.properties.load_imf:
				imf_count = 0
			if not self.properties.load_cd:
				cd0_count = 0

			for i in range(cd0_count):
				cd0s = cd0.add(i * 0x80)
				#print("cd0 @ {}".format(cd0s))
				import cdcmesh
				mat = struct.unpack_from("<ffffffffffffffff", cd0.section.payload, cd0s.offset)
				bbs = struct.unpack_from("<ffffffffffff", cd0.section.payload, cd0s.offset + 64)
				cd1 = cd0.deref(0x74)
				#print("cd1 @ {}".format(cd1))
				vtx = cd1.deref(0x20)
				idx = cd1.deref(0x24)

				vertexdata = vtx.section.payload # assume whole section
				indices = idx.section.payload # assume whole section
				indices += b"\0" * ((-len(indices)) % 12)
				#print("vertexdata @ {}".format(vtx))
				#print("indices @ {}".format(idx))
				#print(mat)
				#print(bbs)
				name = "{}_cd{}".format(filepath, i)
				mesh = cdcmesh.read_collisionmesh(context, name, vertexdata, indices, False)
				obj = bpy.data.objects.new(name, mesh)
				obj.matrix_world = mk_matrix(mat)
				#scene.collection.objects.link(obj)
				cd_collection.objects.link(obj)


			for i in range(obj_count):
				posrot = struct.unpack_from("<fffLfffLfffLH",
					obj_.section.payload,
					obj_.offset + i*0x70)
				rot = posrot[0:3]
				pos = posrot[4:7]
				scl = posrot[8:11]
				index = posrot[12]
				mat = [ # ignoring rot for now
					scl[0], 0, 0, 0,
					0, scl[1], 0, 0,
					0, 0, scl[2], 0,
					pos[0], pos[1], pos[2], 1
				]
				print(pos, rot, scl, index, objlist.get(index, ""))
				if index in objlist:
					fname = objlist[index] + ".drm"
					# obj_sections, obj_root_section_index = db.load(fname)
					# obj_root_section = obj_sections[obj_root_section_index]
					# obj_root_section.pay
					objs.append((mat, fname, "obj"))

			float4x4 = struct.Struct("<ffffffffffffffff").unpack_from

			for i in range(imf_count):
				mat = imf.access(float4x4, i*0x90)
				dtpid = imf.access(uint32, i*0x90 + 0x48)[0]
				try:
					print("{}/{} (dtp: {:04x}) @ {}".format(i, imf_count, dtpid, imf))
					fname = imf.deref(0x4C+i*0x90).access_null_terminated().decode("ascii")
					#print(mat, fname)
					objs.append((mat, fname, "imf"))
				except:
					print("getting path failed for obj #", i)

			for mat, fname, category in objs:
				m = mk_matrix(mat)

				if isinstance(fname, drm.Reference):
					n = "section.{}".format(fname.get_id())
				else:
					n = os.path.basename(fname.replace("\\", "/"))

				if True: # lod to layers
					i = 0
					for mesh in meshes_for(fname): #name, mesh
						name = "{}.lod{}".format(n, i)
						obj = bpy.data.objects.new(name, mesh)
						obj.matrix_world = m
						if category == "imf":
							z = min(i, len(lod_collections)-1)
							print(i, z, len(lod_collections))
							lod_collections[z].objects.link(obj)
						elif category == "occlusion":
							occ_collection.objects.link(obj)
						elif category == "cell":
							unit_mesh_collection.objects.link(obj)
						else:
							non_imf_collection.objects.link(obj)
						#if category == "obj":
						#	break
						i += 1
				else: # lod to game engine lods
					def gamelods(meshes):
						lods = []
						for i, mesh in enumerate(meshes):
							if i == 0: continue
							name = "{}.lod{}".format(n, i)
							obj = bpy.data.objects.new(name, mesh)
							obj.layers[0] = False
							obj.layers[19] = True
							lods.append(obj)

						def instanciate(m):
							if len(meshes) == 0:
								bpy.ops.object.empty_add(type="PLAIN_AXES")
								bpy.context.object.matrix_world = m
								return bpy.context.object
							obj = bpy.data.objects.new(n, meshes[0])
							obj.matrix_world = m
							scene.collection.objects.link(obj)
							oldactive = bpy.context.scene.objects.active
							bpy.context.scene.objects.active = obj
							for i, (dist, lodobj) in enumerate(zip([2.5, 5.0, 8.0, 13.0, 18.0, 25.0, 40.0], lods)):
								bpy.ops.object.lod_add()
								bpy.context.object.lod_levels[i+1].object = lodobj
								bpy.context.object.lod_levels[i+1].distance = dist
							bpy.context.scene.objects.active = oldactive
							return obj
							
						return instanciate

					meshes_for(fname, fun=gamelods)(m)

			if rel:
				for i in range(rel_count):
					name = rel.access_null_terminated(0x100 * i).decode("utf-8")
					print("rel", name)
			else:
				print("no rel")

		bpy.context.view_layer.update()

		return {'FINISHED'}

def menu_func_import(self, context):
	self.layout.operator(UnitImporter.bl_idname, text="CDC Unit (.drm)")

def register():
	bpy.types.Mesh.cdcorigin = bpy.props.StringProperty()
	bpy.utils.register_class(UnitImporter)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
	bpy.utils.unregister_class(UnitImporter)
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
	register()
