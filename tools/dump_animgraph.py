import sys
import struct
import drm

# try tools/dump_animgraph.py pc-w/player_everyman.drm

with open(sys.argv[1], "rb") as f:
	data = f.read()

if data[0:4] == b"CDRM":
	data = drm.cdrm(data)

sections, root_index = drm.read(data)

def deref(ref, optoff = 0):
	section_index, offset = ref
	offset += optoff
	section = sections[section_index]
	if offset not in section.fixupinfo:
		print("couldn't deref {:x}:{:x}".format(section_index, offset))
		assert False
	_, target_index, target_offset = section.fixupinfo[offset]
	return (target_index, target_offset)

def dword(ref, optoff = 0):
	section_index, offset = ref
	offset += optoff
	return struct.unpack("<L", sections[section_index].payload[offset:offset+4])[0]

def add(ref, off):
	a, b = ref
	return (a, b+off)

def p(ref):
	return "{:5x} {:5x}".format(*ref)

entry = (root_index, 0)

objblobsub_dtp = deref(entry)


animGraphBase    = deref(objblobsub_dtp, 0x4C) # AnimGraphRequest*
numAnimGraphsExt = dword(objblobsub_dtp, 0x50)
animGraphsExt    = deref(objblobsub_dtp, 0x54)

# print(p(objblobsub_dtp))
# print(p(animGraphBase))
# print(p(animGraphsExt))
# print(p(deref(animGraphsExt)))
# print()

animGraphs = []
animGraphs.append(deref(animGraphBase))
for i in range(0, numAnimGraphsExt):
	animGraphs.append(deref(animGraphsExt, 8*i))

dotname = "anim.dot"
dot = open(dotname, "w")
print("digraph {", file=dot)
print(" rankdir=LR;", file=dot)

nmi = ["notimpl_input_{}".format(i) for i in range(10)]
nmo = ["notimpl_output_{}".format(i) for i in range(10)]

lr = True
def node(name, label, ni, no):
	ri = "{"+"|".join("<i{0}>in{0}".format(i) for i in range(ni))+"}"
	ro = "{"+"|".join("<o{0}>out{0}".format(o) for o in range(no))+"}"
	rlabel = ri+"|"+label+"|"+ro
	if lr:
		rlabel = "{"+rlabel+"}"
	print("    {} [shape=\"record\" label=\"{}\"]".format(name, rlabel), file=dot)

	ri = ["{}:i{}".format(name, i) if i<ni else name for i in range(12)]
	ro = ["{}:o{}".format(name, o) if o<no else name for o in range(12)]
	return ri, ro

def print_outernode(n, prefix): # see animnode_instantiate_outer
	nodeType = dword(n, 4)
	nodeData = deref(n, 8)

	print("  outer", p(n), "type", nodeType, "data", p(nodeData))
	if nodeType == 0:
		return print_subnodes(nodeData, prefix=prefix)
	else:
		print("unhandled outer node", nodeType, file=sys.stderr)

	# 1 graph
	# 2 transientstate
	# 3 --
	# 4 fragment
	# 5 empty

	return nmi, nmo

def print_innernode(i, n, prefix):
	dot_name = "{}leaf_{:x}_{:x}".format(prefix, *n)

	nodeType = dword(n, 4)
	if nodeType in (0, 3):
		return print_leafnode(i, n, dot_name=dot_name)
	elif nodeType == 1:
		subnodes = deref(n, 8)
		return print_subnodes(subnodes, prefix=dot_name)
	elif nodeType == 2:
		subgraph = deref(n, 8)
		dot_label = "{:x}:{:x}:subgraph:{:x}:{:x}".format(n[0], n[1], subgraph[0], subgraph[1])
		return node(dot_name, dot_label, 0, 1)
	else:
		print("unhandled inner node", nodeType, file=sys.stderr)

	return nmi, nmo

def print_leafnode(i, n, dot_name): # see animnode_instantiate_type_0_3
	path = deref(n, 8)
	path = sections[path[0]].payload[path[1]:].split(b"\0", 1)[0]
	path = path.decode("utf-8")
	name = path.split("\\")[-1].split(".")[0]
	print("      [{}] {} {}".format(i, p(n), name))
	
	ni = 1
	no = 1

	if path == "cdc\\dtp\\animnodes\\AnimDrivenRagdoll.dtp":
		ni = 2
	elif path == "cdc\\dtp\\animnodes\\Blend.dtp":
		dataC = deref(n, 12)
		x = dword(dataC, 0)
		if x <= 8:
			blend_oddity_1 = [1, 2, 2, 1, 2, 2, 2, 2]
			blend_oddity_2 = [2, 3, 4, 3, 6, 9, 5, 6]
			#                 3  4  6  4  8 11  7  8
			ni = blend_oddity_1[x] + blend_oddity_2[x]
		else:
			ni = 1
	elif path == "cdc\\dtp\\animnodes\\BoneSet.dtp":
		ni = 2
	elif path == "cdc\\dtp\\animnodes\\EmptyFragment.dtp":
		ni = 0
	elif path == "cdc\\dtp\\animnodes\\FaceFxNode.dtp":
		ni = 3
	elif path == "cdc\\dtp\\animnodes\\Fragment.dtp":
		dataC = deref(n, 12) # AnimFragmentNodeBlob *
		
		ni = 0
	elif path == "cdc\\dtp\\animnodes\\Hosted.dtp":
		ni = 1
	elif path == "cdc\\dtp\\animnodes\\Mirror.dtp":
		ni = 2
	elif path == "cdc\\dtp\\animnodes\\Modifier.dtp":
		ni = 2 # or 0, it depends
	elif path == "cdc\\dtp\\animnodes\\OverlayPose.dtp":
		ni = 4
	elif path == "cdc\\dtp\\animnodes\\Ragdoll.dtp":
		ni = 2
	elif path == "cdc\\dtp\\animnodes\\RagdollData.dtp":
		ni = 0
	elif path == "cdc\\dtp\\animnodes\\Sync.dtp":
		ni = 1

	elif path == "dtp\\animnodes\\AdditiveLookAt.dtp":
		ni = 10
	elif path == "dtp\\animnodes\\AutoHosted.dtp":
		ni = 1
	elif path == "dtp\\animnodes\\BlendValue.dtp":
		ni = 1
	elif path == "dtp\\animnodes\\BoneController.dtp":
		ni = 3
	elif path == "dtp\\animnodes\\ConditionalFragment.dtp":
		ni = 0
	elif path == "dtp\\animnodes\\DX3RagdollData.dtp":
		ni = 0
	elif path == "dtp\\animnodes\\DynamicFragment.dtp":
		ni = 0
	elif path == "dtp\\animnodes\\InstanceHosted.dtp":
		ni = 1
	elif path == "dtp\\animnodes\\LookAt.dtp":
		ni = 17
	elif path == "dtp\\animnodes\\MirrorExtended.dtp":
		ni = 3
	elif path == "dtp\\animnodes\\QuadrupedRNode.dtp":
		ni = 3
	elif path == "dtp\\animnodes\\SmartFragment.dtp":
		ni = 0
	elif path == "dtp\\animnodes\\SmartHosted.dtp":
		ni = 1
	elif path == "dtp\\animnodes\\SmartMovement.dtp":
		ni = 12
	elif path == "dtp\\animnodes\\SmartVariable.dtp":
		ni = 1

	else:
		assert False

	dot_label = "{:x}:{:x}:{}".format(n[0], n[1], name)
	return node(dot_name, dot_label, ni, no)

dot_do = True

def print_subnodes(n, prefix):
	dot_name = "{}_group_{:x}_{:x}".format(prefix, *n)

	numNodes   = dword(n, 0x0)
	numEdges   = dword(n, 0x4)
	numInputs  = dword(n, 0x8)
	numOutputs = dword(n, 0xC)
	print("   ", "#nodes={} #edges={} #inputs={} #outputs={}".format(
		numNodes,
		numEdges,
		numInputs,
		numOutputs
	))
	innerNodes = deref(n, 0x10)
	innerEdges = deref(n, 0x14)

	if dot_do:
		print("  subgraph cluster_{} {{".format(dot_name), file=dot)

	inports = []
	outports = []
	innerports = []

	for i in range(numInputs):
		dot_port_name = "{}_in{}".format(dot_name, i)
		if dot_do:
			print("    {} [ label=\"[in {}]\" ];".format(dot_port_name, i), file=dot)
		inports.append(dot_port_name)

	for i in range(numOutputs):
		dot_port_name = "{}_out{}".format(dot_name, i)
		if dot_do:
			print("    {} [ label=\"[out {}]\" ];".format(dot_port_name, i), file=dot)
		outports.append(dot_port_name)

	for i in range(0, numNodes):
		ports = print_innernode(i, add(innerNodes, 20*i), prefix=dot_name+"_")
		innerports.append(ports)

	for i in range(0, numEdges):
		edge = add(innerEdges, 24*i)
		src_node = dword(edge, 0)
		src_port = dword(edge, 4)
		dst_node = dword(edge, 8)
		dst_port = dword(edge, 12)
		unk1 = dword(edge, 16)
		unk2 = dword(edge, 20)
		unk = "{:x}/{:x}".format(unk1, unk2)

		src_port_list = innerports[src_node][1] if src_node != 0xffffffff else inports
		dst_port_list = innerports[dst_node][0] if dst_node != 0xffffffff else outports

		if dot_do:
			print("    {} -> {} [ label=\"{}\" ]".format(
				src_port_list[src_port],
				dst_port_list[dst_port],
				unk), file=dot)

		# execlink2 [shape="record" label="{Link\<ScriptExec\>|{<n>next|<x>exec}}"]

	if dot_do:
		print("  }", file=dot)


	print()

	return inports, outports

animGraphs2 = []
for g in animGraphs:
	if g not in animGraphs2:
		animGraphs2.append(g)
animGraphs = animGraphs2

#animGraphs = [(0x2e2, 0)]

for g in animGraphs:
	print("graph", p(g))
	g_dot_name = "g_{:x}_{:x}".format(*g)
	print(" subgraph cluster_{} {{".format(g_dot_name), file=dot)
	numOuter = dword(g, 0)
	outerArray = deref(g, 4)
	for i in range(0, numOuter):
		outer = add(outerArray, i*20)
		print_outernode(outer, prefix=g_dot_name)
	print(" }", file=dot)

print("}", file=dot)
dot.close()
print()
print("graphviz data written to", dotname)
