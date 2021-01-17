from decompiler_signature import Signature, script_type_name, Decl
from decompiler_symbols import symbols

import struct
uint32 = struct.Struct("<I").unpack_from
uint16 = struct.Struct("<H").unpack_from

class PrimitiveTy:
	def __init__(self, name):
		self.name = name
	def __repr__(self):
		return self.name

u8 = PrimitiveTy("u8")
u16 = PrimitiveTy("u16")
u32 = PrimitiveTy("u32")
idk1 = PrimitiveTy("idk1")
_str = PrimitiveTy("str")
_bool = u8 #PrimitiveTy("bool")
f32 = PrimitiveTy("f32")
unk = PrimitiveTy("unknown")
any_ty = None

i32 = u32 # oops

def convertible_script_type(db, dst, src):
	if dst == src: return True
	dst = db.lookup(8, dst)
	src = db.lookup(8, src)
	srcs = [src]
	while src:
		if dst == src:
			print(dst, srcs, True)
			return True
		src = src.deref(0x18) # get parent
		srcs.append(src)
	print(dst, srcs, False)
	return False

class PointerTy:
	def __init__(self, target, tag=""):
		self.target = target
		self.tag = tag
	def __eq__(self, other):
		return isinstance(other, PointerTy) and \
			self.target == other.target
	def __repr__(self):
		return "{!r} *{}".format(self.target, self.tag)

class WrappedObject:
	def __init__(self, s_id):
		self.s_id = s_id
	def __eq__(self, other):
		return isinstance(other, WrappedObject) and \
			(self.s_id == other.s_id or None in (self.s_id, other.s_id))
	def convertible(self, db, from_type):
		return isinstance(from_type, WrappedObject) and \
			convertible_script_type(db, self.s_id, from_type.s_id)
	def __repr__(self):
		if self.s_id:
			return "wrapped{:x}".format(self.s_id)
		else:
			return "wrapped(None)"

class UnwrappedObject:
	def __init__(self, s_id):
		self.s_id = s_id
	def __eq__(self, other):
		return isinstance(other, UnwrappedObject) and \
			(self.s_id == other.s_id or None in (self.s_id, other.s_id))
	def __repr__(self):
		if self.s_id:
			return "unwrapped{:x}".format(self.s_id)
		else:
			return "unwrapped(None)"

pidk1  = PointerTy(idk1)
pobj   = WrappedObject(None)
pother = UnwrappedObject(None)

class Expr:
	def __init__(self, fmt, *args):
		args = [str(arg) for arg in args]
		self.str = fmt.format(*args)

	def __str__(self):
		return self.str

def imm_read(ctx, args):
	instruction = ctx.ip.access(uint32)[0]
	offset = instruction & 0xffffff
	opcode = instruction >> 24
	if opcode == 0x02:
		value = ctx.ip.access(uint32, 4)[0]
	elif opcode == 0x03:
		value = offset if offset < 0x800000 else offset - 0x1000000
	elif opcode == 0x04:
		value = offset & 0xff
	elif opcode == 0x05:
		value = ctx.ip.deref(4).access_null_terminated().decode("utf-8")

	e = Expr("")
	e.str = repr(value)
	return e
	#return call_expr("imm_read", args)

def local_read(ctx, args):
	instruction = ctx.ip.access(uint32)[0]
	offset = instruction & 0xffffff
	name = "unknown_local_{:x}".format(offset)
	ty = None
	for l_offset, l_name, l_decl in ctx.local_decls:
		if l_offset == offset:
			name = l_name
			ty = decl_to_type(l_decl)
	e = Expr(name)
	e.ty = ty
	return e
	#return call_expr("local_read", args)

def with_addr(f):
	def wrapper(ctx, args):
		e = f(ctx, args)
		if hasattr(e, "ty"):
			e.ty = PointerTy(e.ty)
		e.str = "&"+e.str
		return e
	return wrapper

local_addr = with_addr(local_read)

def this(ctx, args):
	print("using this in", hex(ctx.this_id))
	e = Expr("this")
	e.ty = WrappedObject(ctx.this_id)
	return e

def new(ctx, args):
	ty = ctx.ip.deref(4)
	e = Expr("new {}".format(script_type_name(ty)))
	e.ty = wrapped_script_type(ty)
	return e

def this_member_read(ctx, args):
	instruction = ctx.ip.access(uint32)[0]
	offset = instruction & 0xffffff
	name = "unknown_member_{:x}".format(offset)
	ty = None
	for l_offset, l_name, l_entry in ctx.member_decls:
		if l_offset == offset:
			name = l_name
			#ty = decl_to_type(l_entry.init.decl)
			ty = unwrapped_script_type(l_entry.objty)
	e = Expr("this->"+name)
	e.ty = ty
	return e
	#return call_expr("this_member_read", args)

this_member_addr = with_addr(this_member_read)

def obj_member_read(ctx, args):
	import q_decompiler
	instruction = ctx.ip.access(uint32)[0]
	offset = instruction & 0xffffff

	this = getattr(args[0], "ty", None)
	name = "unknown_member_{:x}".format(offset)
	ty = None
	if this is not None:
		assert isinstance(this, PointerTy)
		script = ctx.db.lookup(8, this.target.s_id)
		noprint = lambda *args, **kwargs: None
		s = q_decompiler.decompile(ctx.db, script, noprint, path=None, decompile_functions=False)
		for f_offset, f_name, entry in s.fields:
			if offset == f_offset:
				name = f_name
				ty = decl_to_type(entry.init.decl)
	e = Expr("{}->"+name, args[0])
	if ty: e.ty = ty
	return e

obj_member_addr = with_addr(obj_member_read)
other_member_read = obj_member_read
other_member_addr = with_addr(obj_member_read)

def indirect_read(ctx, args):
	return call_expr("indirect_read", args)

def indirect_addr(ctx, args):
	return call_expr("indirect_addr", args)

def binop(op):
	def f(ctx, args):
		lhs, rhs = args
		return Expr("{} "+op+" {}", lhs, rhs)

	return f

def unaryop(op):
	def f(ctx, args):
		arg, = args
		return Expr("{}{{}}".format(op), arg)

	return f

def castop(tyname):
	return unaryop("("+tyname+")")

def ty_mismatch(ty1, ty2, arg):
	return Expr("mismatch<{}, {}>({{}})".format(ty1, ty2), arg)

def call_expr(fname, args):
	fmt = ", ".join("{}" for arg in args)
	return Expr(fname + "(" + fmt + ")", *args)

def gcref_assign(ctx, args):

	return Expr("{} = {}", *args)

pobj = None

simple_opcodes = {
	0x00: ([],            [],       None),
	0x01: ([any_ty],      [],       None),
	0x02: ([],            [u32],    imm_read),
	0x03: ([],            [u32],    imm_read),
	0x04: ([],            [u8],     imm_read),
	0x05: ([],            [_str],   imm_read),

	0x06: ([],            [u8],     local_read),
	0x07: ([],            [u16],    local_read),
	0x08: ([],            [u32],    local_read),
	0x09: ([],            [pidk1],  local_addr),
	0x0A: ([],            [_str],   local_read), # not correct probably

	0x0B: ([],            [None],   this),

	0x0C: ([],            [u8],     this_member_read),
	0x0D: ([],            [u16],    this_member_read),
	0x0E: ([],            [u32],    this_member_read),
	0x0F: ([],            [pidk1],  this_member_addr),
	0x10: ([],            [_str],   this_member_read),

	0x11: ([pobj],        [u8],     obj_member_read),
	0x12: ([pobj],        [u16],    obj_member_read),
	0x13: ([pobj],        [u32],    obj_member_read),
	0x14: ([pobj],        [pidk1],  obj_member_addr),
	0x15: ([pobj],        [_str],   obj_member_read),

	0x16: ([pother],      [u8],     other_member_read),
	0x17: ([pother],      [u16],    other_member_read),
	0x18: ([pother],      [u32],    other_member_read),
	0x19: ([pother],      [pidk1],  other_member_addr),
	0x1A: ([pother],      [_str],   other_member_read),

	0x1B: ([pother, u32], [u8],     indirect_read),
	0x1C: ([pother, u32], [u16],    indirect_read),
	0x1D: ([pother, u32], [u32],    indirect_read),
	0x1E: ([pother, u32], [pidk1],  indirect_addr),
	0x1F: ([pother, u32], [_str],   indirect_read),

	0x20: None, #
	0x21: None, #
	0x22: None, #

	0x23: None, # string copy
	0x24: None, # string copy
	0x25: None, # string copy
	0x26: None, # string copy
	0x27: None, # string copy
	0x28: None, # string copy

	0x29: None, #
	0x2A: None, #
	0x2B: None, #
	0x2C: None, #
	0x2D: None, #

	0x2E: None, # byte assign
	0x2F: None, # dword assign
	0x30: ([None, None],  [],       gcref_assign),
	0x31: None, # string ref assign   StringHandle::change
	0x32: None, # map ref? assign     ScriptMapImpl::handover
	0x33: None, # array ref? assign   ScriptDynArrayImpl::handover
	0x34: None, # 
	0x35: None, # struct ref? assign
	0x36: None, # memcpy
	0x37: None, # gc ref assign multiple

	0x38: None, #
	0x39: None, #
	0x3A: None, #
	0x3B: None, #
	0x3C: None, #
	0x3D: ([u32],          [u32],   unaryop("-")), # int negate
	0x3E: ([u32, u32],     [u32],   binop("+")),   # int add
	0x3F: ([u32, u32],     [u32],   binop("-")),   # int sub
	0x40: ([u32, u32],     [u32],   binop("*")),   # int mul
	0x41: ([u32, u32],     [u32],   binop("/")),   # int div
	0x42: ([u32, u32],     [u32],   binop("%")),   # int mod
	0x43: ([u32, u32],     [_bool], binop("<=")),  # int <= ?
	0x44: ([u32, u32],     [_bool], binop("<")),   # int < ?
	0x45: ([u32, u32],     [_bool], binop("==")),  # int ==
	0x46: ([_bool, _bool], [_bool], binop("==")),  # bool ==
	0x47: ([f32],          [f32],   unaryop("-")), # float negate
	0x48: ([f32, f32],     [f32],   binop("+")),   # float add
	0x49: ([f32, f32],     [f32],   binop("-")),   # float sub
	0x4A: ([f32, f32],     [f32],   binop("*")),   # float mul
	0x4B: ([f32, f32],     [f32],   binop("/")),   # float div
	0x4C: ([f32, f32],     [_bool], binop("<=")),  # float <=
	0x4D: ([f32, f32],     [_bool], binop("<")),   # float <
	0x4E: ([f32, f32],     [_bool], binop("==")),  # float ==
	0x4F: ([_str, _str],   [_bool], binop("==")),  # strcmp
	0x50: ([_bool],        [_bool], unaryop("!")), # bool negate
	0x51: ([_bool, _bool], [_bool], binop("&&")),  # &&
	0x52: ([_bool, _bool], [_bool], binop("||")),  # ||
	0x53: ([_bool, _bool], [_bool], binop("xor")), # xor
	0x54: ([u32, u32],     [u32],   binop("&")),   # &
	0x55: ([u32, u32],     [u32],   binop("|")),   # |
	0x56: ([u32, u32],     [u32],   binop("^")),   # ^
	0x57: ([u32, u32],     [u32],   binop("<<")),  # <<
	0x58: ([u32, u32],     [u32],   binop(">>")),  # >>
	0x59: ([u32],          [u32],   unaryop("~")), # ~
	0x5A: ([f32],          [i32],   castop("int")), # float -> int32_
	0x5B: ([f32],          [_bool], castop("bool")),  # != 0.0
	0x5C: ([i32],          [f32],   castop("float")),   # int32_t -> float
	0x5D: ([i32],          [_bool], castop("bool")),  # != 0
	0x5E: ([_bool],        [i32],   castop("int")),   # bool -> int32_t
	0x5F: ([_bool],        [f32],   castop("float")), # bool -> float

	0x60: None, #
	0x61: None, #
	0x62: None, #

	# 63 64              j, jz
	# 65 66 67 68 69 6A  calls
	# 6B 6C 6D 6E 6F 70  calls
	# 71 72 73 74 75 76  calls

	0x77: None, #
	0x78: None, #
	0x79: None, #
	0x7A: None, #
	0x7B: ([], [], None),
	0x7C: None, #
	0x7D: None, #
	# 7E dynamic cast
	0x7F: ([],             [None],  new),
	0x80: None, #
	0x81: None, #
	0x82: None, #
	0x83: None, #
	0x84: None, #
	0x85: None  #
}

def decl_to_type(decl):
	assert isinstance(decl, Decl)
	if decl.name == "string": return _str
	if decl.name == "bool":  return _bool
	if decl.name == "dword": return u32
	if decl.name == "float": return f32
	if decl.name == "byte":  return u8
	if (decl.ty & 15) == 0x0a:
		return unwrapped_script_type(decl.tyext)
	elif (decl.ty & 15) == 0x0b:
		return PointerTy(wrapped_script_type(decl.tyext))
	elif (decl.ty & 15) == 0x0f:
		return u32
	assert False, hex(decl.ty)

def wrapped_script_type(scriptref):
	return scriptref and WrappedObject(scriptref.section.s_id)

def unwrapped_script_type(scriptref):
	return scriptref and UnwrappedObject(scriptref.section.s_id)

def type_match(db, ty1, ty2):
	if ty1 is None:
		return True
	if ty2 is None:
		return True
	while isinstance(ty1, PointerTy) and isinstance(ty2, PointerTy):
		ty1 = ty1.target
		ty2 = ty2.target
	if hasattr(ty1, "convertible"):
		if ty1.convertible(db, ty2):
			return True
	return ty1 == ty2

class Context:
	pass

def build_expr(db, ip, stmt_list, expr_stack, stack_delta, member_decls, local_decls):

	ctx = Context()
	ctx.db = db
	ctx.ip = ip
	ctx.local_decls = local_decls
	ctx.member_decls = member_decls
	ctx.this_id = ip.get_id()

	type_stack = []
	iip = ip
	instruction = ip.access(uint32)[0]
	opcode = instruction >> 24;
	payloadZX = instruction & 0xFFFFFF
	payloadSX = payloadZX if payloadZX < 0x800000 else payloadZX - 0x1000000
	ip = ip.add(4)

	simple = simple_opcodes.get(opcode, None)
	if simple:
		pop_ty, push_ty, build_node = simple

		args = []
		for ty in reversed(pop_ty):
			expr = expr_stack.pop()
			if not type_match(db, ty, expr.ty):
				expr = ty_mismatch(ty, expr.ty, expr)
			args.insert(0, expr)

		if build_node:
			node = build_node(ctx, args)
			assert len(push_ty) <= 1
			if push_ty:
				if not hasattr(node, "ty"):
					node.ty = push_ty[0]
				expr_stack.append(node)
			else:
				stmt_list.append(node)

	elif opcode == 0x7e:
		arg = expr_stack.pop()
		assert arg.ty, arg
		ty = ip.deref(0)
		ip = ip.add(4)
		ty = wrapped_script_type(ty)
		if ty:
			ty = PointerTy(ty)
		if type_match(db, ty, arg.ty):
			expr_stack.append(arg)
		else:
			expr = Expr("dynamic_cast<"+str(ty)+", "+str(arg.ty)+">({})", arg)
			expr.ty = ty
			expr_stack.append(expr)
		assert expr_stack[-1].ty

	elif 0x65 <= opcode <= 0x76:
		call_type = (opcode - 0x65) % 6

		has_return = (0x65 <= opcode <= 0x6A)
		has_this   = call_type in (0, 4, 5)
		is_virtual = call_type in (2, 3, 5)
		is_native  = call_type == 0

		if call_type in (0, 1, 4):
			z = ip.deref(0)
			if z:
				called_signature = z.deref(0)
			else:
				# patched using cdc::NativeBuiltInImpl
				z = ip.access(uint32)[0]
				assert z & 1
				nty = (z >> 8) & 0xFF
				method = z >> 16
				called_signature = {
					(7, 0): ("ScriptDynArrayImpl::size",   True,  0),
					(7, 1): ("ScriptDynArrayImpl::clear",  False, 0),
					(7, 2): ("ScriptDynArrayImpl::resize", False, 1),
					(7, 3): ("ScriptDynArrayImpl::remove", False, 1),
					(7, 4): ("ScriptDynArrayImpl::push",   False, 1),
					(7, 5): ("ScriptDynArrayImpl::pop",    False, 0),
					(8, 0): ("ScriptMapImpl::size",        True,  0),
					(8, 1): ("ScriptMapImpl::clear",       False, 0),
					(8, 2): ("ScriptMapImpl::find",        True,  1),
					(8, 3): ("ScriptMapImpl::erase",       False, 1)
				}[nty, method]

			ip = ip.add(4)

		elif call_type in (3, 5):
			called_signature = ip.deref(0)
			ip = ip.add(4)

		elif call_type == 2:
			called_signature = ip.deref(4)
			ip = ip.add(8)

		pop_ty = []

		cs = Signature(called_signature, symbols)
		decl = cs.q_desc

		if cs.ret.name == "void":
			has_return = False

		if has_return:
			pop_ty.append((True, decl_to_type(cs.ret)))
		for arg in cs.args:
			pop_ty.append((False, decl_to_type(arg)))
		if has_this:
			# to-do: in some calls wrapped is correct, in others unwrapped is
			pop_ty.append((False, unwrapped_script_type(called_signature.add(-called_signature.offset))))

		args = []
		for output, ty in reversed(pop_ty):
			expr = expr_stack.pop()
			ty = PointerTy(ty)
			if output:
				dstty, srcty = expr.ty, ty
			else:
				dstty, srcty = ty, expr.ty
			if not type_match(db, dstty, srcty):
				expr = ty_mismatch(dstty, srcty, expr)
			args.insert(0, expr)

		fname = cs.methodname

		if has_return and has_this:
			fmt = ", ".join("{}" for i in range(len(args)-2))
			stmt = Expr("{} = {}->{}("+fmt+")", args[0], args[-1], fname, *args[1:-1])
		elif has_return:
			fmt = ", ".join("{}" for i in range(len(args)-1))
			stmt = Expr("{} = {}("+fmt+")", args[0], fname, *args[1:])
		elif has_this:
			fmt = ", ".join("{}" for i in range(len(args)-1))
			stmt = Expr("{}->{}("+fmt+")", args[-1], fname, *args[:-1])
		else:
			stmt = call_expr(fname, args)

		stmt_list.append(stmt)

	elif opcode == 0x63:
		target = ip.add(4 * payloadSX).offset
		stmt_list.append(Expr("jump {:x}".format(target)))

	elif opcode == 0x64:
		arg = expr_stack.pop()
		if not type_match(db, _bool, arg.ty):
			arg = ty_mismatch(_bool, arg.ty, arg)
		target = ip.add(4 * payloadSX).offset
		stmt_list.append(Expr("if not ({{}}) jump {:x}".format(target), arg))

	elif stack_delta < 0:
		y = len(expr_stack)
		if len(expr_stack) > -stack_delta:
			args = expr_stack[stack_delta-1:]
			del expr_stack[stack_delta-1:]
			node = call_expr("opcode{:02x}".format(opcode), args)
			node.ty = None
			expr_stack.append(node)
		else:
			args = expr_stack[stack_delta:]
			del expr_stack[stack_delta:]
			node = call_expr("opcode{:02x}".format(opcode), args)
			stmt_list.append(node)
		z = len(expr_stack)
		assert z-y == stack_delta, (stack_delta, y, z)
	else:
		for i in range(stack_delta):
			e = Expr("opcode{:02x}_result{}".format(opcode, i))
			e.ty = None
			expr_stack.append(e)
