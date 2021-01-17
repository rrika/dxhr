import struct
from decompiler_symbols import object_scripts

uint32 = struct.Struct("<I").unpack_from
uint16 = struct.Struct("<H").unpack_from

def script_type_name(script):
	name = script.deref(0x10)
	if name is not None:
		return name.access_null_terminated().decode("utf-8")
	elif script.section.s_id in object_scripts:
		return "%{}%".format(object_scripts[script.section.s_id])
	else:
		return "Unknown{:04X}".format(script.section.s_id)

def id_name(symbols, name_a, name_b, fmt, *fmtargs):
	ok = name_a == name_b and name_a in symbols

	name_a = symbols.get(name_a, "{:04x}".format(name_a))
	name_b = symbols.get(name_b, "{:04x}".format(name_b))

	if ok:
		return name_a
	elif name_a == name_b:
		return fmt.format(name_a, *fmtargs)
	else:
		return fmt.format(name_a+"_"+name_b, *fmtargs)

unpack_decl = struct.Struct("<BBxxHHxxxxHH").unpack_from

class Decl:
	def __init__(self, ref, symbols={}, decltype="decl"):
		ty, count, w4, w6, offset, w14 = ref.access(unpack_decl)
		tyext = ref.deref(0x8)

		self.ty = ty
		self.tyext = tyext
		self.tyarg = None
		self.nameid4 = w4
		self.nameid14 = w14
		self.member_offset = offset

		self.varname = id_name(symbols, w4, w14, decltype+"_{}_{:x}", offset)

		self.name = {
			 0: "void",
			 1: "bool",
			 2: "dword",
			 3: "float",
			 4: "string",
			 5: "byte",
			 6: "array",
			 7: "ScriptDynArrayImpl",# used in sas_scanner_a.drm
			 8: "ScriptMapImpl", 
			 9: "unknown9", # type param? (used in ScriptDynArrayImpl::push argument)
			10: "Object",
			11: "GCObject",
			12: "struct",
			13: "RCObject", # dtpref
			14: "unknown14",
			15: "enum",
		}[ty & 0xf]
		self.basename = self.name

		if (ty & 0xf) == 7:
			self.tyarg = tyarg = Decl(tyext)
			self.basename = self.name
			self.name += "<" + tyarg.name + ">"

		elif (ty & 0xf) in (10, 11, 15):

			if ty & 0x80:

				self.name = script_type_name(tyext.deref(0)) or self.name
				self.tyarg = tyarg = Decl(tyext.deref(4))
				self.tyext = tyext.deref(0)
				self.basename = self.name
				self.name += "<" + tyarg.name + ">"
			else:
				self.name = script_type_name(tyext) or self.name
				self.basename = self.name

		elif (ty & 0xf) == 12:
			assert False, "never encountered"
			inits = tyext.deref(0xc)
			num_inits = inits.access(uint32, -1)[0]
			subdecls = []
			for i in range(num_inits):
				subdecl = Decl(inits.add(0x14 * i))
				subdecls.append(subdecl.name)
			self.name += " {"
			self.name += ", ".join(subdecls)
			self.name += "}"


class Init:
	def __init__(self, ref, symbols={}, decltype="decl"):
		self.decl = Decl(ref, symbols, decltype)
		self.name = self.decl.name
		self.member_offset = self.decl.member_offset

		value = ref.add(0x10)
		self.valueref = value
		self.value = "TODO({:02X})".format(self.decl.ty & 15)

		ty = self.decl.ty
		fmt = {1: "<B", 2: "<I", 3: "<f", 5: "<B"}.get(ty & 0xf, None)
		if fmt:
			self.value = value.access(struct.Struct(fmt).unpack_from)[0]
			if (ty & 0xf) == 1:
				self.value = {0: False, 1: True}[self.value]

class Entry:
	def __init__(self):
		self.init = None
		self.objty = None

class Type:
	pass


class Signature:
	def __init__(self, signature, symbols, i=-1):
		self.read_from(signature, symbols, i)

	def read_from(self, signature, symbols, i=-1):
		self.sigref = signature

		async5 = signature.access(uint16, 0x5)[0] & 0xff
		tableindex = signature.access(uint16, 0x6)[0]
		if i == -1:
			i = tableindex
		name8 = signature.access(uint16, 0x8)[0]
		nameA = signature.access(uint16, 0xa)[0]

		classname = script_type_name(signature.deref(0))
		methodname = id_name(symbols, name8, nameA, "method_{}_{:x}", i)

		ret_ty = signature.add(0x10)
		ret = Decl(ret_ty)
		args = signature.deref(0xC)
		argdecls = []
		args_ = []
		if args:
			num_args = args.access(uint32, -4)[0]
			for j in range(num_args):
				arg = args.add(0x14*j)
				try:
					argdecl = Decl(arg, symbols, "arg")
					argdecls.append(argdecl)
					args_.append("{} {}".format(argdecl.name, argdecl.varname))

				except Exception as e:
					args_.append("%")
		uq_signature_str = "{} {}({})".format(ret.name, methodname, ", ".join(args_))
		q_signature_str = "{} {}::{}({})".format(ret.name, classname, methodname, ", ".join(args_))
		if async5:
			uq_signature_str = "async " + uq_signature_str
			q_signature_str = "async " + q_signature_str

		self.uq_desc = uq_signature_str
		self.q_desc = q_signature_str

		self.args = argdecls
		self.methodname = methodname
		self.ret = ret
		self.async_ = async5
