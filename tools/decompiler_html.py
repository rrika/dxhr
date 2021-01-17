import sys, os, io, struct, html

import drm
import decompiler
from decompiler_symbols import symbols

def html_page(title, body):
	return f"""<!DOCTYPE html>
<html>
<head>
	<title>{title}</title>
	<style>
	.mono {{ font-family: monospace; }}
	</style>
</head>
<body>
{body}
</body>
</html>
"""

def html_type(ty, path, nsection, more_html, see_also):
	see_also_html = [
		f"{link_kind} {html_link_script(target)}<br/>\n"
		for (link_kind, target) in see_also
	]
	see_also_html.sort()

	return html_page(
		title="DXHR: Type {:08x}".format(ty.own_id),
		body=f"""
		<h1>{ty.classname}</h1>
		<pre>./tools/drmexplore pc-w/ {path} n$[0x{"{:x}".format(nsection)}]i
		</pre>
		<h2>Interface</h2>
		{more_html}
		<h2>Interface (text version)</h2>
		<pre>{html.escape(ty.info)}</pre>
		<h2>See also</h2>
		{"".join(see_also_html)}
		""".strip()
	)

def html_units(units):
	html_unit = ""
	for unit in units:
		html_unit += f"<h2>{unit.name}</h2>\n"
		for unitobj in unit.objects:
			html_unit += '<a style="font-family: monospace" name="{0:08x}">{0:08x}</a>: '.format(unitobj.dword38)
			html_unit += link_type(unitobj.script_id, unitobj.name)
			html_unit += html.escape(repr(unitobj.ref))
			html_unit += '<br/>\n'
			for use in unitobj_xrefs.get(unitobj.dword38, []):
				html_unit += f'<span style="margin-left: 4em;">referenced in {html_link_script(use)}</span><br/>\n'

	return html_page(
		title='DXHR: Unit Objects',
		body=html_unit)

def html_index(types):
	return html_page(
		title="DXHR: Class List",
		body="".join(
			'<span class="mono">{:08x}: </span>{}<br/>\n'.format(ty.own_id, link_type(ty.own_id, ty.classname))
			for ty in types
		))

def html_scenarios(scenarios):
	body = ""
	for scn_id, names in scenarios:
		body += "<p><b>Scenario {:x}</b><br/>\n".format(scn_id)
		body += "".join(html.escape(name)+"<br/>\n" for name in names)
		body += "".join(html_link_script(xref)+"<br/>\n" for xref in scenario_xrefs.get(scn_id, []))

	return html_page(
		title="DXHR: Scenarios",
		body=body)

def html_objectives():
	body = ""
	for (name, descr), xrefs in objective_xrefs.items():
		body += f"<p><b>{html.escape(name)}</b><br/>\n"
		body += f"{html.escape(descr)}<br/>\n"
		body += "".join(html_link_script(xref)+"<br/>\n" for xref in xrefs)
		body += "</p>"

	return html_page(
		title="DXHR: Objectives",
		body=body)

def html_missions():
	body = ""
	for (name, descr), xrefs in mission_xrefs.items():
		body += f"<p><b>{html.escape(name)}</b><br/>\n"
		body += f"{html.escape(descr)}<br/>\n"
		body += "".join(html_link_script(xref)+"<br/>\n" for xref in xrefs)
		body += "</p>"

	return html_page(
		title="DXHR: Missions",
		body=body)

types = []
units = []
tyxrefs = {}

scenario_xrefs = {}
objective_xrefs = {}
mission_xrefs = {}
method_xrefs = {}
unitobj_xrefs = {}

def html_signature(sig):
	ret = sig.ret
	methodname = sig.methodname
	return "{} {}({})".format(
		html_link_decl(ret),
		methodname,
		", ".join(html_link_decl(argdecl) for argdecl in sig.args)
	)

def write_scripts(types):
	for ty in types:

		if ty.parent:
			mh = "<pre>class {} : {} {{\n".format(ty.classname, html_link_script(ty.parent))
		else:
			mh = "<pre>class {} {{\n".format(ty.classname)

		for offset, name, entry in ty.fields:
			mh += "    "
			if entry.init and entry.init.decl and entry.init.decl.tyext:
				mh += html_link_decl(entry.init.decl)
			elif entry.objty:
				mh += html_link_script(entry.objty)
			else:
				mh += html_link_decl(entry.init.decl)
			mh += " " + name
			if entry.init:
				mh += " = {};\n".format(getattr(entry.init, "value_html", entry.init.value))
			else:
				mh += ";\n"

		for s in ty.signatures:
			mh += "    {};\n".format(html_signature(s))
			for xref in method_xrefs.get(s.sigref, []):
				#mh += "    // referenced at {}\n".format(link_type(xref.sigref.section.s_id, html_signature(xref)))
				mh += "    // referenced at {}\n".format(link_type(xref.sigref.section.s_id, xref.q_desc))
		mh += "}</pre>\n"

		t = html_type(ty=ty, path=ty.path[5:], nsection=ty.script.section.index,
			more_html=mh, see_also=set(tyxrefs.get(ty.own_id, [])))

		with open("html/type{:08x}.html".format(ty.own_id), "w") as f:
			f.write(t)

def write_index(types):
	i = html_index(types)
	with open("html/index.html", "w") as f:
		f.write(i)

def write_scenario_index(scenarios):
	i = html_scenarios(scenarios=scenarios)
	with open("html/scenarios.html", "w") as f:
		f.write(i)

def write_objective_index():
	i = html_objectives()
	with open("html/objectives.html", "w") as f:
		f.write(i)

def write_mission_index():
	i = html_missions()
	with open("html/missions.html", "w") as f:
		f.write(i)

def write_units():
	units_s = units[:]
	units_s.sort(key=lambda u: min(o.dword38 for o in u.objects))
	i = html_units(units_s)
	with open("html/units.html", "w") as f:
		f.write(i)

def link_type(i, l):
	return "<a href=\"type{:08x}.html\">{}</a>".format(i, l)

def html_link_decl(decl):
	if decl.tyext is None:
		return html.escape(decl.name)
	else:
		tyid = decl.tyext.section.s_id
		h = ""
		if decl.ty&15 == 15:
			h += "enum "
		if decl.ty&15 == 11:
			h += "gcref "
		h += link_type(tyid, html.escape(decl.basename))
		if decl.tyarg:
			h += "&lt;"
			h += html_link_decl(decl.tyarg)
			h += "&gt;"
		return h

def html_link_script(target):
	if target is None:
		return "null"
	s_id = target.section.s_id
	return link_type(
		s_id, decompiler.script_type_name(target))

uint32 = struct.Struct("<I").unpack_from
uint16 = struct.Struct("<H").unpack_from

db = drm.DB("mnt2")

def main():
	os.makedirs("html/", exist_ok=True)
	for i, n in enumerate(sys.argv[1:]):
		print(n)

		#try:
		secs, root_sec = db.load(n)
		#except Exception as e:
		#	print(e)
		#	continue

		if True:
			for j, sec in enumerate(secs):
				#if b"pirate_radio" in sec.payload:
				#	print(hex(j), hex(sec.s_id))
				if sec.typeid == 8: # script
					script = drm.Reference(secs, sec, 0)
					load_script(db, script, n)
		if True:
			unit = drm.Reference(secs, secs[root_sec], 0)
			k = load_unit(unit, n)
			if k:
				units.append(k)

objlist = {}
with open("pc-w/objectlist.txt") as f:
	for line in f.read().split("\n")[1:]:
		try:
			num, name = line.split(",", 1)
			objlist[int(num)] = name
		except:
			print(line)

drmname_to_scriptid = {}

def object_get_script_id(drmname):

	if drmname in drmname_to_scriptid:
		return drmname_to_scriptid[drmname]

	try: secs, root_sec = db.load(drmname)
	except: return

	obj = drm.Reference(secs, secs[root_sec], 0)
	dtp = obj.deref(0)
	sid = dtp.access(uint16, 0xc0)[0]

	drmname_to_scriptid[drmname] = sid
	return sid

class Unit:
	pass
class UnitObject:
	pass

def load_unit(unit, unitname):

	unitsub30 = unit.deref(0x30)
	if not unitsub30:
		print("not unit sub 30 here")
		return
	num_unit_objects = unitsub30.access(uint32, 0x14)[0]
	unit_objects = unitsub30.deref(0x18)

	unit_objects_k = []
	for i in range(num_unit_objects):

		unit_object = unit_objects.add(0x70 * i)

		unit_objlistindex = unit_object.access(uint16, 0x30)[0]
		unit_word32 = unit_object.access(uint16, 0x32)[0]
		unit_dword34 = unit_object.access(uint32, 0x34)[0]
		unit_dword38 = unit_object.access(uint32, 0x38)[0]
		unit_dword3C = unit_object.access(uint32, 0x3C)[0]

		if unit_objlistindex not in objlist:
			continue
		object_name = objlist[unit_objlistindex]
		sid = object_get_script_id("pc-w/{}.drm".format(object_name))
		k = UnitObject()
		k.ref = unit_object
		k.name = object_name
		k.script_id = sid
		k.dword38 = unit_dword38
		unit_objects_k.append(k)

		#print("unit object", i, unit_objlistindex, object_name)
		#print("  {:04x} {:08x} {:08x} {:08x} {:04x}".format(unit_word32, unit_dword34, unit_dword38, unit_dword3C, sid))

		tyxrefs.setdefault(sid, []).append(("unit object #{}".format(i), None))

	k = Unit()
	k.name = unitname[5:]
	k.objects = unit_objects_k
	return k

def process_entry_init(script, init):
	valueref = init.valueref
	if init.decl.name.startswith("objective"):
		if valueref.deref(0):
			objective_id = valueref.deref(0).deref(0).access(uint16)[0]
			objective = db.lookup(7, objective_id)
			if objective:
				string_a = objective.access(uint16, 0)[0]
				string_b = objective.access(uint16, 2)[0]
				string_a = lookup_string(string_a)
				string_b = lookup_string(string_b)
				objective_xrefs.setdefault((string_a, string_b), []).append(script)
			else:
				pass # why

	elif init.decl.name.startswith("scenarioref"):
		scn_id = valueref.deref(0).deref(0).access(uint16)[0]
		scenario_xrefs.setdefault(scn_id, []).append(script)

	elif init.decl.name.startswith("mission"):
		mission = valueref.deref(0).deref(0).deref(0)
		string_title = mission.access(uint16, 0)[0]
		string_descr = mission.access(uint16, 2)[0]
		string_title = lookup_string(string_title)
		string_descr = lookup_string(string_descr)
		mission_xrefs.setdefault((string_title, string_descr), []).append(script)

	elif init.decl.name.startswith("instanceref"):
		unitobj_id = valueref.deref(0).deref(0).access(uint32)[0]
		unitobj_xrefs.setdefault(unitobj_id, set()).add(script)
		init.value_html = '{{<a href="units.html#{0:08x}">unit object {0:08x}</a>}}'.format(unitobj_id)

	elif init.decl.name in ("uberobjectevent", "uberobjectcommand"):
		id0 = valueref.deref(0).deref(0).access(uint16, 0)[0]
		id1 = valueref.deref(0).deref(0).access(uint32, 4)[0]
		init.value_html = '{{<a href="type{0:08x}.html">type {0:08x}</a>, {1:x}}}'.format(id0, id1)

	elif init.decl.name == "smartscript":
		ssi = valueref.deref(0).deref(0)
		if ssi.access(uint32, 16)[0] or ssi.deref(0):
			if ssi.access(uint32, 16)[0]:
				dtb_b = ssi.add(4)
				where = 'local'
			else:
				dtb_b = ssi.deref(0).add(0x1C)
				where = 'persistent(dtp:{:04X})'.format(dtb_b.get_id())
			ty = dtb_b.access(uint32, 3)[0] & 0xff
			vl = dtb_b.add(4)
			ty = {5: "bool", 7: "dword"}.get(ty, ty)
			init.value_html = '{} {{type={}}}'.format(where, ty)
		else:
			init.value_html = 'empty'

	elif init.decl.name == "sound":
		dtp_id = valueref.deref(0).deref(8).access(uint16)[0]
		sound_dtp = db.lookup(7, dtp_id)
		if sound_dtp:
			sound_dtp_4 = sound_dtp.deref(4)
			if sound_dtp_4:
				sound_dtp_4_0 = sound_dtp_4.deref(0)
				if sound_dtp_4_0:
					sound_dtp_4_0_4 = sound_dtp_4_0.deref(4)
					if sound_dtp_4_0_4:
						name = sound_dtp_4_0_4.deref(0)
						if name:
							name = name.access_null_terminated().decode("utf-8")
							init.value_html = 'dtp:{:04X}:{}'.format(dtp_id, name)
						else:
							init.value_html = 'dtp:{:04X}:Z'.format(dtp_id)
					else:
						init.value_html = 'dtp:{:04X}:Y'.format(dtp_id)
				else:
					init.value_html = 'dtp:{:04X}:X'.format(dtp_id)
			else:
				init.value_html = 'dtp:{:04X}:W'.format(dtp_id)
		else:
			init.value_html = 'dtp:{:04X}:V'.format(dtp_id)

done_scripts = set()

def load_script(db, script, path):

	if script.section.s_id in done_scripts:
		return

	done_scripts.add(script.section.s_id)

	f = io.StringIO()
	def print_into(*args, **kwargs):
		return print(*args, **kwargs, file=f)

	t = decompiler.decompile(db, script, print_into, path)
	t.info = f.getvalue()
	types.append(t)
	if t.parent is not None:
		tyxrefs.setdefault(t.parent.section.s_id, []).append(("derived class", script))
		tyxrefs.setdefault(t.own_id, []).append(("parent class", t.parent))
	for offset, name, entry in t.fields:
		zs = []
		if entry.objty:
			zs = [entry.objty]
		elif entry.init.decl.tyext:
			zs = [entry.init.decl.tyext]
		if entry.init and entry.init.decl.tyarg:
			zs.append(entry.init.decl.tyarg.tyext)

		for z in zs:
			if not z:
				continue # why
			if entry.init:
				link = "initialized field in"
				if entry.init.decl.ty&15 == 12:
					print("found something in", t.classname)

			else:
				link = "field in"
			tyxrefs.setdefault(z.section.s_id, []).append((
				link, script))

			if entry.init:
				process_entry_init(script, entry.init)

	for s in t.signatures:
		for d in s.args:
			if d.ty&15 == 12:
				print("found something in", t.classname)
			if d.tyext is not None:
				r = d.tyext.section.s_id
				tyxrefs.setdefault(r, []).append(("argument to method on", script))
		for sig in s.calling:
			if isinstance(sig, tuple): # ScriptDynArrayImpl or ScriptMapImpl
				continue
			#cs = decompiler.Signature(sig, symbols, 0x9999)
			method_xrefs.setdefault(sig, []).append(s)

scenarios = []
objdb, objdb_root = db.load("pc-w/objective_database.drm")
scndb, scndb_root = db.load("pc-w/scenario_database.drm")


with open(os.path.join(db.basepath, "pc-w/local/locals.bin"), "rb") as f:
	stringtable = f.read()

def lookup_string(i):
	start, stop = struct.unpack_from("<II", stringtable, 4*i)
	s = stringtable[start:stop-1]
	s = s[:500]
	try:
		s = s.decode("utf-8")
	except:
		s = repr(s)
	return s

from scenarios import read_scenarios
for scn_id, _, _, names in read_scenarios(db, scndb, scndb_root):
	scenarios.append((scn_id, names))

main()

write_scripts(types)
write_index(types)
write_units()
write_scenario_index(scenarios)
write_objective_index()
write_mission_index()
