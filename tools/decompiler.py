import os
import struct
import sys

import drm

from decompiler_signature import *
from decompiler_symbols import symbols, object_scripts
from decompiler_ast import build_expr, Expr

Reference = drm.Reference

real_print = print
def decompile(db, script, print, path=None, decompile_functions=True):

	# 0x00: scriptTypeVersion
	# 0x04:   ???
	# 0x08: id8 / idA
	# 0x0C: string path
	# 0x10: string name
	# 0x14: script type self
	# 0x18: script type parent
	# 0x1C: size of member variables
	# 0x20:   ???
	# 0x24:   ???
	# 0x28:   ???
	# 0x2C: member initializers (for construction)
	# 0x30: member layout (for garbage collection / destruction)
	# 0x34:   ???
	# 0x38:   ???
	#   0x3C: index
	#   0x40: field4 / field6
	#   0x44: scriptTableTable
	# 0x48: array of referenced script types
	# 0x4C: ??? / packageId
	#
	# the indented part may be referenced by certain call opcodes to indicate
	# they want to call the method implementation of a particular super-class

	t = Type()
	t.parentref = parent = script.deref(0x18)
	sizeof_members = script.access(uint16, 0x1c)[0]

	num_inits = num_layout = 0
	inits = script.deref(0x2c)
	layout = script.deref(0x30)
	main_func_table = script.deref(0x38)
	if inits:
		num_inits = inits.access(uint32, -4)[0]
	if layout:
		num_layout = layout.access(uint32, -4)[0]

	t.script = script
	t.path = path

	classname = script_type_name(script)
	if decompile_functions:
		real_print(classname)

	t.classname = classname
	t.parent = parent
	t.own_id = script.section.s_id
	if parent:
		parentclassname = script_type_name(parent)
		print("class {} : {} {{".format(classname, parentclassname))
	else:
		print("class {} {{".format(classname))

	print("    // sizeof = 0x{:x}".format(sizeof_members))

	full_layout = {}

	for i in range(num_inits):
		init = Init(inits.add(0x14*i))
		e = full_layout.setdefault(init.member_offset, Entry())
		e.init = init

	for i in range(num_layout):
		member_ty = layout.deref(8*i)
		member_offset = layout.access(uint32, 8*i + 4)[0]
		e = full_layout.setdefault(member_offset, Entry())
		e.objty = member_ty

	member_names = {}
	t.fields = []
	for offset, entry in sorted(full_layout.items()):
		if entry.objty:
			n = script_type_name(entry.objty)
		else:
			n = entry.init.name
		name = "field_{:x}".format(offset)
		if entry.init and entry.init.decl:
			name = entry.init.decl.varname

		if entry.init and entry.init.decl:
			name = symbols.get(entry.init.decl.nameid14, name)

		t.fields.append((offset, name, entry))
		if entry.init:
			print("    {} {} = {};".format(n, name, entry.init.value))
		else:
			print("    {} {};".format(n, name))
		#print("  {} {}; // {:4x}".format(n, name, offset))
		member_names[offset] = name

	t.signatures = []
	t.functions = []
	if main_func_table:
		num_funcs = main_func_table.access(uint32, -4)[0]
		for i in range(num_funcs):
			func = main_func_table.add(0x1c * i)
			signature = func.deref(0x0)
			bytecode = func.deref(0x18)
			local_inits = func.deref(0xc)

			s = Signature(signature, symbols, i)
			s.calling = set()
			t.signatures.append(s)

			signature_str = s.uq_desc

			print("    " + signature_str, end="")
			if not bytecode:
				print("; // no bytecode")
			elif not decompile_functions:
				print("; // skipped decompilation")
			else:
				asts = decompile_function(db, s, bytecode, t, local_inits, print)
				t.functions.append((s, asts))

	print("};")

	return t

def scan_bytecode(ip):
	seen = set()
	boundaries = {(ip, 0)}
	explore = {(ip, 0)}
	while explore:
		ip, sp = explore.pop()
		if ip in seen:
			continue
		if not ip.valid():
			continue
		seen.add(ip)

		ss, next_ip, called, stack_delta = skip_bytecode_inst(ip)
		sp += stack_delta
		for nip in next_ip:
			explore.add((nip, sp))
		for nip in next_ip[1:]:
			boundaries.add((nip, sp))
	return boundaries

def skip_bytecode_inst(ip, member_names={}, local_names={}):
	iip = ip
	instruction = ip.access(uint32)[0]
	opcode = instruction >> 24;
	payloadZX = instruction & 0xFFFFFF
	payloadSX = payloadZX if payloadZX < 0x800000 else payloadZX - 0x1000000
	ip = ip.add(4)


	# 65 66 67 68 69 6A
	# 6B 6C 6D 6E 6F 70
	# 71 72 73 74 75 76
	# f  f  -s s  f  s
	#    th th th
	# na    v  v     v

	if 0x65 <= opcode <= 0x76:
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

	else:
		called_signature = None


	if opcode in (0x02, 0x05, 0x63, 0x7E):
		ip = ip.add(4)

	if opcode == 0x7b:
		next_ip = tuple()
	elif opcode in (0x63, 0x64):
		next_ip = (ip, ip.add(4 * payloadSX))
	else:
		next_ip = (ip,)

	hexwords = []
	for i in range(0, ip.offset-iip.offset, 4):
		word = iip.access(uint32, i)[0]
		hexwords.append("{:08x}".format(word))
	hexwords = " ".join(hexwords)

	if opcode in (0x00, 0x14, 0x3d, 0x47, 0x50, 0x59, 0x5a, 0x5b, 0x5c, 0x5d, 0x5e, 0x5f, 0x63, 0x77, 0x7b, 0x7c, 0x7e):
		stack_delta = 0
	elif opcode in (0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10):
		stack_delta = 1
	elif opcode in (0x01, 0x3e, 0x3f, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46,
		            0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x51, 0x52,
		            0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x64, 0x80):
		stack_delta = -1
	elif opcode in (0x2e, 0x2f, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38):
		stack_delta = -2
	else:
		stack_delta = 99

	if opcode in (0x06, 0x07, 0x08, 0x0A, 0x09):
		hexwords += " " + local_names.get(payloadZX, "unnamed local {:x}".format(payloadZX))

	if opcode in (0x0B, 0x0C, 0x0D, 0x0F, 0x0E):
		hexwords += " " + member_names.get(payloadZX, "unnamed member {:x}".format(payloadZX))

	if opcode == 0x05:
		n = ip.deref(-4).access_null_terminated()
		try: n = n.decode("utf-8")
		except: n = repr(n)
		hexwords += " " + repr(n)

	if opcode in (0x11, 0x12, 0x13, 0x14, 0x15):
		pass

	if called_signature and isinstance(called_signature, tuple):
		decl, has_return, num_args = called_signature
		hexwords += " " + decl

		stack_delta = - num_args - has_return

	elif called_signature:
		hexwords += " "
		if not has_return:
			hexwords += "(void)"
		if not has_this:
			hexwords += "this->"
		if is_virtual:
			hexwords += "virtual "
		if is_native:
			hexwords += "native "


		cs = Signature(called_signature, symbols)
		decl = cs.q_desc
		#targetname = script_type_name(called_signature.add(-called_signature.offset))
		#hexwords += targetname + "::" + decl
		hexwords += decl
		has_return = has_return and cs.ret.name != "void"

		stack_delta = - len(cs.args) - has_return - has_this

	return hexwords, next_ip, called_signature, stack_delta

def locals_map(s, t, local_inits, print):
	local_decls = []
	local_names = {}

	for arg in s.args:
		local_names[arg.member_offset] = arg.varname
		local_decls.append((arg.member_offset, arg.varname, arg))

	if local_inits:
		num_locals = local_inits.access(uint32, -4)[0]
		for j in range(num_locals):
			local = local_inits.add(0x14 * j)
			local_init = Init(local)
			local_decl = local_init.decl
			if local_decl.nameid4:
				kind = "local"
			else:
				kind = "temp"
			name = "{}_{:x}".format(kind, local_decl.member_offset)
			name = symbols.get(local_decl.nameid4, name)
			if local_init.value is not None:
				print("        {} {} = {};".format(local_decl.name, name, local_init.value))
			else:
				print("        {} {};".format(local_decl.name, name))
			local_names[local_decl.member_offset] = name
			local_decls.append((local_decl.member_offset, name, local_decl))

	if s.ret.name != "void":
		local_decls.append((0, "return_value", s.ret))

	return local_decls, local_names

discard = lambda e: Expr("(void) {}", e)

class Block:
	def __init__(self):
		self.stmts = []

def decompile_function(db, s, bytecode, t, local_inits, print):
	member_decls = t.fields
	member_names = {} # meh

	print(" {")

	print_bytecode = True
	print_ast = False

	local_decls, local_names = locals_map(s, t, local_inits, print)

	ip = bytecode
	bs = list(scan_bytecode(ip))
	bs.sort(key=lambda ref: ref[0].offset)
	bs_ = {b for b, sp in bs}

	astblocks = {}

	for b, sp in bs:
		if sp != 0:
			real_print("non zero sp at basic block start in", t.classname, s.q_desc)
		ip = b
		if not print_bytecode:
			print("\n        /* {:08x}: */".format(ip.offset))

		expr_stack = []
		stmt_list = []
		def flush_ast():
			bl = astblocks.setdefault(b, Block())
			if not print_ast:
				return
			nonlocal expr_stack, stmt_list
			for expr in expr_stack:
				print("        leftover expr {};".format(expr))
				bl.stmts.append(discard(expr))
			for stmt in stmt_list:
				print("        {};".format(stmt))
				bl.stmts.append(stmt)
			expr_stack = []
			stmt_list = []

		while ip:
			if ip.access(uint32)[0] >> 24 == 0x00:
				if print_bytecode:
					print()
			ss, next_ip, called, stack_delta = skip_bytecode_inst(ip, member_names, local_names)
			if print_ast:
				build_expr(db, ip, stmt_list, expr_stack, stack_delta, member_decls, local_decls)
			if called:
				s.calling.add(called)
			if print_bytecode:
				print("        /* {:08x}: sp {:2} {:+2} */ {}".format(ip.offset, sp, stack_delta, ss))
			if len(next_ip) > 1:
				flush_ast()
			sp += stack_delta
			ip = next(iter(next_ip)) if next_ip else None
			if ip in bs_ or ip is None:
				flush_ast()
				if print_bytecode:
					print("        ---")
				break
		flush_ast()

	print("    }")

	return astblocks


def main():
	db = drm.DB("./")
	for i, n in enumerate(sys.argv[1:]):
		secs, _ = db.load(n)
		for j, sec in enumerate(secs):
			if sec.typeid == 8: # script
				script = Reference(secs, sec, 0)
				decompile(db, script, print)

if __name__ == '__main__':
	main()
