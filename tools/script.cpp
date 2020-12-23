#include <iomanip>
#include <vector>
#include <set>
#include "script.h"

extern std::map<std::pair<uint16_t, uint16_t>, const char*> named_members;
extern std::map<uint16_t, const char*> script_symbol;
extern std::map<uint32_t, const char*> section_header_symbol;

typedef DRM::Section::Reference Reference;
typedef DRM::Section            Section;

/*struct ll { ll *n; Reference& r; };

static void dump32(std::ostream &os, Reference& data, std::string indent, int32_t start, int32_t count, ll* l=nullptr) {

	ll* u = l;
	while (u) {
		if (u->r.section == data.section && u->r.offset == data.offset) {
			os << indent << "recursion detected" << std::endl;
			return;
		}
		u = u->n;
	}

	ll v{l, data};

	for (int32_t i=start; i<count; i++) {
		uint32_t item;
		try {
			item = data.access<uint32_t>(i*4);
		} catch (std::exception& e) {
			break;
		}
		os << indent << std::setfill('0') << std::setw(8) << item << std::setw(0);
		if (item == 0xbeebbeeb) {
			Reference r = data.deref(i*4);
			if (r.section == nullptr) {
				os << " no ref though";
			} else {
				os << " -> (" << r.section->index << ": " << r.offset << ")" << std::endl;
				dump32(os, r, indent+"  ", -1, 4, &v);
			}
		}
		os << std::endl;
	}
}*/
void pdump32(std::ostream &os, Reference& data, std::string indent, int32_t start, int32_t count);
void dumpSignature(std::ostream& os, Reference scriptConfig);
void scriptTypeOneline(std::ostream &os, Reference scriptType);
void scriptTypeName(std::ostream &os, Reference scriptType);

static const char* refToString(Reference r) {
	if (r.section == nullptr)
		return "(null)";
	return &(r.access<char>());
}

static const char* derefToString(Reference r) {
	return refToString(r.deref());
}

/*static void methodPath(std::ostream &os, Reference blob, Reference method) {
	auto numTables       = blob.access<uint16_t>(0x3C);
	Reference tableTable = blob.deref(0x44);
	bool found = false;

	for (uint32_t i=0; i<numTables; i++) {
		// Untested code
		Reference table = tableTable.deref(i*4);
		auto numEntries = table.access<uint32_t>();

		for (uint32_t j=0; j<numEntries; j++) {
			Reference func = table.deref(4+j*4);
			Reference funcConfig = func.deref();
			if (funcConfig.section == method.section && funcConfig.offset == method.offset) {
				os << "#" << method.section->index << "." << i << "." << j;
				found = true;
			}
		}
	}
	if (!found) {
		os << "#" << method.section->index << ".main." << (method.offset - blob.deref(0x38).offset)/0x1C;
	}
}*/

void annotateVar(std::ostream &os, Section* scriptSection, uint32_t offset, std::map<uint16_t, uint16_t>& names) {
	if (auto it = names.find(offset); it != names.end())
		if (auto it2 = script_symbol.find(it->second); it2 != script_symbol.end())
			os << "  // " << it2->second;

	// auto it = named_members.find({scriptSection->header.id, uint16_t(offset)});
	// if (it != named_members.end())
	// 	os << "  // " << it->second;
}

bool formatInstruction(std::ostream &os, std::string indent, Reference& pc, int32_t& jump,
	std::map<uint16_t, uint16_t>& membersNames,
	std::map<uint16_t, uint16_t>& localsNames)
{
	bool terminate = false;
	auto read32 = [&]()->uint32_t{ auto retval = pc.access<uint32_t>(); pc.offset += 4; return retval; };
	auto instruction = read32();
	uint8_t  opcode  = instruction >> 24;
	uint32_t payloadZX = (instruction & 0xFFFFFF);
	int32_t  payloadSX = (((int32_t)instruction) << 8) >> 8;

	os << "   " << std::setfill('0') << std::setw(0) << std::hex;
	switch (opcode) {
		case 0x00:
			os << "nop --------------------- " << std::setw(6) << payloadZX; break;
		case 0x01:
			os << "pop"; break;
		case 0x02:
			os << "push " << std::setw(8) << read32(); break;
		case 0x03:
			os << "push " << std::dec << payloadSX << std::hex; break;
		case 0x04:
			os << "push " << std::setw(2) << (payloadZX & 0xFF); break;
		case 0x05: {
			//auto val = pc.access<uint32_t>();
			os << "push \"" << &pc.deref().access<char>() << "\"" << std::endl;
			pdump32(os, pc, "    ", 0, 1);
			pc.offset += 4;
			break;
		}
		case 0x06:
			os << "push byte[locals+" << payloadZX << "]"; annotateVar(os, pc.section, payloadZX, localsNames); break;
		case 0x07:
			os << "push word[locals+" << payloadZX << "]"; annotateVar(os, pc.section, payloadZX, localsNames); break;
		case 0x08: case 0x0A:
			os << "push [locals+" << payloadZX << "]"; annotateVar(os, pc.section, payloadZX, localsNames); break;
		case 0x09:
			os << "push locals+" << payloadZX << ""; annotateVar(os, pc.section, payloadZX, localsNames); break;

		case 0x0B:
			os << "pop"; break;

		case 0x0C:
			os << "push byte[this+" << payloadZX << "]"; annotateVar(os, pc.section, payloadZX, membersNames); break;
		case 0x0D:
			os << "push word[this+" << payloadZX << "]"; annotateVar(os, pc.section, payloadZX, membersNames); break;
		case 0x0E: case 0x10:
			os << "push [this+" << payloadZX << "]"; annotateVar(os, pc.section, payloadZX, membersNames); break;
		case 0x0F:
			os << "push this+" << payloadZX << ""; annotateVar(os, pc.section, payloadZX, membersNames); break;

		case 0x11:
			os << "push byte[unwrap[sp]+" << payloadZX << "]"; break;
		case 0x12:
			os << "push word[unwrap[sp]+" << payloadZX << "]"; break;
		case 0x13: case 0x15:
			os << "push [unwrap[sp]+" << payloadZX << "]"; break;
		case 0x14:
			os << "push unwrap[sp]+" << payloadZX << ""; break;

		case 0x16:
			os << "push byte[[sp]+" << payloadZX << "]"; break;
		case 0x17:
			os << "push word[[sp]+" << payloadZX << "]"; break;
		case 0x18: case 0x1A:
			os << "push [[sp]+" << payloadZX << "]"; break;
		case 0x19:
			os << "push [sp]+" << payloadZX << ""; break;

		case 0x1B:
			os << "push byte[[sp-1]+[sp-0]]"; break;
		case 0x1C:
			os << "push word[[sp-1]+[sp-0]]"; break;
		case 0x1D: case 0x1F:
			os << "push [[sp-1]+[sp-0]]"; break;
		case 0x1E:
			os << "push [sp-1]+[sp-0]"; break;

		// case 0x20: ??
		// case 0x21: ??
		// case 0x22: ??

		// case 0x23: ??
		// case 0x24: ??
		// case 0x25: ??
		// case 0x26: ??
		// case 0x27: ??
		// case 0x28: ??

		// case 0x29: ??
		// case 0x2A: ??
		// case 0x2B: ??
		// case 0x2C: ??
		// case 0x2D: ??

		case 0x2E:
			os << "byte[[sp-1]] = [sp-0]"; break;
		case 0x30:
			os << "gc ref assign"; break;
		case 0x31:
			os << "string ref assign"; break;
		case 0x32:
			os << "map (ref?) assign"; break;
		case 0x33:
			os << "array (ref?) assign"; break;

		// case 0x34: ??

		case 0x35:
			os << "struct (ref?) assign"; break;
		case 0x36:
			os << "memcpy"; break;
		case 0x37:
			os << "gc ref assign multiple " << payloadZX; break;
		case 0x38:
			os << "string ref assign multiple " << payloadZX; break;

		// case 0x39: ??
		// case 0x3A: ??
		// case 0x3B: ??
		// case 0x3C: ??

		case 0x3D:
			os << "int negate"; break;
		case 0x3E:
			os << "int add"; break;
		case 0x3F:
			os << "int sub"; break;
		case 0x40:
			os << "int mul"; break;
		case 0x41:
			os << "int div"; break;
		case 0x42:
			os << "int mod"; break;
		case 0x43:
			os << "int <= ?"; break;
		case 0x44:
			os << "int < ?"; break;
		case 0x45:
			os << "int =="; break;
		case 0x46:
			os << "bool =="; break;
		case 0x47:
			os << "float negate"; break;
		case 0x48:
			os << "float add"; break;
		case 0x49:
			os << "float sub"; break;
		case 0x4A:
			os << "float mul"; break;
		case 0x4B:
			os << "float div"; break;
		case 0x4C:
			os << "float <="; break;
		case 0x4D:
			os << "float <"; break;
		case 0x4E:
			os << "float =="; break;
		case 0x4F:
			os << "strcmp"; break;
		case 0x50:
			os << "bool negate"; break;
		case 0x51:
			os << "&&"; break;
		case 0x52:
			os << "||"; break;
		case 0x53:
			os << "xor"; break;
		case 0x54:
			os << "&"; break;
		case 0x55:
			os << "|"; break;
		case 0x56:
			os << "^"; break;
		case 0x57:
			os << "<<"; break;
		case 0x58:
			os <<
				">>"; break;
		case 0x59:
			os << "~"; break;
		case 0x5A:
			os << "float -> int32_t"; break;
		case 0x5B:
			os << "!= 0.0"; break;
		case 0x5C:
			os << "int32_t -> float"; break;
		case 0x5D:
			os << "!= 0"; break;
		case 0x5E:
			os << "bool -> int32_t"; break;
		case 0x5F:
			os << "bool -> double"; break;
		case 0x63:
			jump = payloadSX;
			os << "j " << payloadSX;
			//pc.offset += payloadSX*4;
			break;
		case 0x64:
			jump = payloadSX;
			os << "jz " << payloadSX; break;

		case 0x65: case 0x66: case 0x67: case 0x68: case 0x69: case 0x6A:
		case 0x6B: case 0x6C: case 0x6D: case 0x6E: case 0x6F: case 0x70:
		case 0x71: case 0x72: case 0x73: case 0x74: case 0x75: case 0x76:
		{
			int call_type = (opcode - 0x65) % 6;

			// bool has_return = 0x65 <= opcode && opcode <= 0x6A;
			bool has_this   = call_type == 0 || call_type == 4 || call_type == 5;
			bool is_virtual = call_type == 2 || call_type == 3 || call_type == 5;
			bool is_native  = call_type == 0;

			os << "call ";
			if (!has_this)
				os << "own ";
			if (is_native)
				os << "native ";
			if (is_virtual)
				os << "virtual ";
			os << "method";
			if (call_type == 2)
			{
				os << " (in specific vtable; super call?)";
				pc.offset += 4;
			}
			if (is_virtual)
			{
				os << " vtable[";
				Reference signature = pc.deref();
				auto tableIndex = signature.access<uint16_t>(6);
				os << tableIndex << "][this[0]]: ";
				// os << std::endl;
				// pdump32(os, signature, "    ", 0, 4);
				dumpSignature(os, signature);
				os << std::endl;
				pc.offset += 4;
			}
			else
			{
				os << ": ";
				Reference function = pc.deref();
				if (function.section) {
					auto signature = function.deref();
					dumpSignature(os, signature);
					//auto methodThisType = signature.deref(0);
					//auto methodThisName = refToString(methodThisType.deref(0x10));
					//os << methodThisName << " ";
					//methodPath(os, methodThisType, r);
				} else {
					os << "0x" << std::setw(8) << pc.access<uint32_t>() << std::setw(0);
				}
				os << std::endl;
				pc.offset += 4;
			}
			break;
		}

		case 0x7B:
			os << "end script"; // probably
			terminate = true;
			break;

		case 0x7E:
			os << "dynamic cast to ";
			scriptTypeOneline(os, pc.deref());
			pc.offset += 4;
			break;

		default:
			os << std::setw(2) << (uint32_t)opcode << "   ";
			os << std::setw(6) << payloadZX << std::setw(0);
			break;
	}
	os << std::endl;
	return terminate;
}

void scriptReport(std::ostream &os, DRM::DRM& drm) {
	for (Section& sec: drm) {
		scriptReportS(os, sec);
	}
}

void printref(std::ostream &os, Reference r);

void scriptTypeOneline(std::ostream &os, Reference scriptType) {
	if (scriptType.section == nullptr) {
		os << "(null)";
		return;
	}

	//const char *rpath = refToString(scriptType.deref(0x0C));
	//const char *rname = refToString(scriptType.deref(0x10));
	os << scriptType.section->origin << " " << scriptType.section->index << " ";
	scriptTypeName(os, scriptType);
	//os << rname; // << " : " << rpath;
	/*os << scriptType.section->index << "/" << scriptType.offset << std::endl;
	dump32(os, scriptType, "   ", 0, 7);*/
}

void scriptTypeName(std::ostream &os, Reference scriptType) {
	if (scriptType.section == nullptr)
		os << "(null)";
	auto name = scriptType.deref(0x10);
	auto it = section_header_symbol.find(scriptType.section->header.id);
	if (name.section == nullptr && it != section_header_symbol.end())
		os << "%" << it->second << "%";
	else
		os << refToString(name);
}

void scriptTypeFuncName(std::ostream &os, Reference scriptTypeFunc) {
	auto scriptType = scriptTypeFunc.deref(0);
	auto ext = scriptTypeFunc.deref(4);
	scriptTypeName(os, scriptType);
	os << refToString(scriptType.deref(0x10));
	auto a = ext.access<uint32_t>(0);
	auto b = ext.access<uint32_t>(4);
	auto tt = ext.deref(8);
	os << "<" << a << "; " << b << "; ";
	scriptTypeName(os, tt);
	os << ">";
}

void dumpId(std::ostream& os, uint16_t id) {
	auto it = script_symbol.find(id);
	if (it == script_symbol.end())
		os << std::setfill('0') << std::setw(4) << id;
	else
		os << it->second;
}

void dumpInitType(std::ostream &os, Reference scriptInit) {
	auto type   = scriptInit.access<uint8_t>(0);
	auto count  = scriptInit.access<uint8_t>(1);
	auto field4 = scriptInit.access<uint16_t>(4);
	auto ptr8   = scriptInit.deref(8);
	os << std::setw(2) << (int)type << ":";
	dumpId(os, field4);
	os << ":";
	if (count != 0 && type != 6) {
		os << "count=" << (int)count << ":";
	}
	switch (type & 0xf) {
		case 0x0: os << "void"; break; // maybe
		case 0x1: os << "byte1"; break;
		case 0x2: os << "dword2"; break;
		case 0x3: os << "float"; break;
		case 0x4: os << "string"; break;
		case 0x5: os << "byte5"; break;
		case 0x6: os << "array[" << (int)count << "]"; break;
		case 0x7: os << "ScriptDynArrayImpl"; break;
		case 0x8: os << "ScriptMapImpl"; break;
		case 0xA: goto with_type;
		case 0xB: os << "GCObject:"; goto with_type;
		case 0xC: os << "struct"; break;
		case 0xD: os << "RCObject"; break;
		case 0xE: os << "dword14"; break;
		case 0xF: os << "enum:"; goto with_type;
		with_type:
			if (type & 0x80) {
				scriptTypeFuncName(os, ptr8);
			} else {
				scriptTypeName(os, ptr8);
			}
			break;
		default: break;
	}
}

extern DRM::Database db;

void dumpInit(std::ostream &os, std::string indent, Reference& scriptInit, bool isLocal) {
	auto indent_next = indent + "  ";
	//pdump32(os, scriptInit, indent, 0, 0x14/4);
	auto type   = scriptInit.access<uint8_t>( 0);
	auto count  = scriptInit.access<uint8_t>( 1);
	auto field4 = scriptInit.access<uint32_t>(4);
	auto ptr8   = scriptInit.deref(8);
	auto target = scriptInit.access<uint16_t>(12);
	auto id14 = scriptInit.access<uint16_t>(14);
	auto value  = Reference{scriptInit.section, scriptInit.offset+16};

	if (!isLocal) {
		os << indent << std::setw(3) << target;
		os << " field4=" << std::setfill('0') << std::setw(8) << field4;
		os << " name="; dumpId(os, id14);
		os << " " << (type>>4) << ":" << (type&0xf) << ":";
	} else {
		// apparently the layouts differ and I never realized until the names showed up wrong
		os << indent << std::setw(3) << target;
		os << " name="; dumpId(os, field4 & 0xffff);
		os << " field6="; dumpId(os, field4 >> 16);
		os << " field14=" << std::setfill('0') << std::setw(4) << id14;
		os << " " << (type>>4) << ":" << (type&0xf) << ":";

	}
	switch (type & 0xf) {
		case 0x1: os << "byte/bool " << (int)value.access<uint8_t>(); break;
		case 0x2: os << "dword " << &value.access<uint32_t>(); break;
		case 0x3: os << "float " << value.access<float>(); break;
		case 0x4: os << "string " << &value.access<char>(); break;
		case 0x5: os << "byte/bool " << (int)value.access<uint8_t>(); break;
		case 0x6: os << "array [" << (int)count << "]";
			for (uint32_t i=0; i<count; i++) {
				Reference innerInit{ptr8.section, ptr8.offset+0x14*i};
				dumpInit(os, indent_next, innerInit, isLocal);
			}
			break;
		case 0x7: os << "ScriptDynArrayImpl"; break;
		case 0x8: os << "ScriptMapImpl"; break;
		case 0xB: os << "GCObject:";
		case 0xA: {
			if (type & 0x80) {
				Reference ptr8b{ptr8.section, ptr8.offset+4};
				ptr8 = ptr8.deref();
				ptr8b = ptr8b.deref();
				auto a = ptr8b.access<uint32_t>(0);
				auto b = ptr8b.access<uint32_t>(4);
				auto tt = ptr8b.deref(8);
				scriptTypeOneline(os, ptr8);
				os << "<" << a << "; " << b << "; ";
				scriptTypeOneline(os, tt);
				os << ">";
			} else {
				scriptTypeOneline(os, ptr8);
			}
			os << std::endl;

			pdump32(os, value, indent_next, 0, 1);
			break;
		}
		case 0xC: os << "ScriptInit struct"; break;
		case 0xD: os << "RCObject"; break;
		case 0xE: os << "dword " << &value.access<uint32_t>(); break;
		case 0xF: os << "dword " << &value.access<uint32_t>(); break;
		default: break;
	}
	os << std::endl;
}

void dumpSignature(std::ostream& os, Reference scriptConfig) {
	auto args = scriptConfig.deref(0xC);
	auto argCount = args.section && args.offset >= 4 ? args.access<uint32_t>(-4) : 0;
	if (scriptConfig.access<uint8_t>(5) != 0)
		os << "async "; // it means the stack frame will be put on the heap
	if (false)
	{
		auto retType = scriptConfig.deref(0x18);
		auto implicitArg = scriptConfig.access<uint16_t>(16) & 0xf;
		if (implicitArg != 0)
			os << "implicitarg(0x" << implicitArg << ") ";
		os << std::setfill('0') << std::setw(4) << scriptConfig.access<uint16_t>(0x14) << ":"; 
		if (retType.section)
			scriptTypeName(os, retType);
		else
			os << "void";
	} else {
		Reference retType = scriptConfig;
		retType.offset += 0x10;
		dumpInitType(os, retType);
	}
	os << " ";
	if (auto ty = scriptConfig.deref(0); ty.section) {
		auto id = ty.section->header.id;
		if (auto name = ty.deref(0x10); name.section) {
			scriptTypeName(os, ty);
		} else if (auto it = section_header_symbol.find(id); it == section_header_symbol.end()) {
			os << "[" << ty.section->origin << "/" << ty.section->index << ":";
			os << std::setfill('0') << std::setw(4) << id << "]";
		} else {
			os << "%" << it->second << "%";
		}
	}
	os << "::";
	if (false) {
		//os << name;
	} else {
		os << "method_";
		os << std::setfill('0') << std::setw(2) << (int)scriptConfig.access<uint8_t>(4) << "_";
		os << std::setfill('0') << std::setw(2) << (int)scriptConfig.access<uint8_t>(5) << "_";
		os << std::setfill('0') << std::setw(4) << scriptConfig.access<uint16_t>(6) << "_"; // scriptTableIndex
		if (scriptConfig.access<uint16_t>(8) != scriptConfig.access<uint16_t>(0xA)) {
			dumpId(os, scriptConfig.access<uint16_t>(8)); os << "_";   // id8
		}
		dumpId(os, scriptConfig.access<uint16_t>(0xA)); // idA
		// os << "_" << std::setfill('0') << std::setw(8) << scriptConfig.access<uint32_t>(0x10); // flags
	}
	os << "(";
	for (unsigned j=0; j<argCount; args.offset += 0x14, j++) {
		os << "[" << args.access<uint16_t>(12) << "]=";
		dumpInitType(os, args);
		os << ";";
		dumpId(os, args.access<uint16_t>(14));
		if (j != argCount-1)
			os << ", ";
	}
	os << ")";
	//os << std::endl;
	//pdump32(os, scriptConfig, "    ", 0, 7);
}

void dumpFunction(std::ostream& os, Reference func, std::map<uint16_t, uint16_t>& membersNames) {
	Reference funcConfig = func.deref();
	auto flags = func.access<uint16_t>(4);
	auto localBytes = func.access<uint16_t>(6);
	auto field8 = func.access<uint16_t>(8);
	auto stackDwords = func.access<uint16_t>(0xa);
	auto locals = func.deref(0xc);
	Reference bytecode   = func.deref(0x18);

	os << "   implements: "; dumpSignature(os, funcConfig); os << std::endl;
	os << "   flags: " << flags << std::endl;
	os << "   field8: " << field8 << std::endl;
	os << "   stackDwords: " << stackDwords << std::endl;

	std::map<uint16_t, uint16_t> localsNames;

	if (locals.section == nullptr) {
		os << "   no locals (" << localBytes << " total)" << std::endl;
	} else {
		os << "   locals (" << localBytes << " total):" << std::endl;
		auto localCount = locals.access<uint32_t>(-4);
		for (unsigned j=0; j<localCount; locals.offset += 0x14, j++) {

			localsNames[locals.access<uint16_t>(12)] = locals.access<uint16_t>(4);

			os << "    locals+" << locals.access<uint16_t>(12) << ": ";

			os << "@ " << std::setfill('0') << std::setw(4) << locals.offset;

			//dumpInitType(os, locals);
			os << "\n"; dumpInit(os, "     ", locals, true); os << "    ";
			os << std::endl;
		}
	}

	if (bytecode.section == nullptr) {
		os << "   no bytecode" << std::endl;
		return;
	}
	os << "   @ " << bytecode.offset << std::endl;

	std::set<uint32_t> done {};
	std::set<uint32_t> targets {0};

	while (!targets.empty()) {
		uint32_t k = *targets.begin();
		targets.erase(targets.begin());
		if (done.find(k) != done.end())
			continue;
		done.insert(k);

		//uint32_t opcode;
		int32_t jump = 0;
		try {
			Reference bytecode_ = bytecode;
			bytecode_.offset += k*4;
			bool terminate = formatInstruction(os, "   ", bytecode_, jump, membersNames, localsNames);
			k = (bytecode_.offset - bytecode.offset) / 4;
			if (!terminate)
				targets.insert(k);
			if (jump != 0)
				targets.insert(k+jump);
		} catch (std::exception& e) {
			os << "   out of range " << std::setw(8) << (bytecode.offset + k*4) << std::endl;
			break;
		}
		//os << "   " << std::setfill('0') << std::setw(8) << opcode << std::setw(0) << std::endl;
	}
}

void scriptReportS(std::ostream &os, Section& sec) {

	os << std::hex;

	if (sec.header.type != Section::ContentType::Script)
		return;

	//dumpFixups(os, sec);

	const char *path = derefToString(Reference{&sec, 0x0C});
	const char *name = derefToString(Reference{&sec, 0x10});
	Reference scriptInit = Reference{&sec, 0x2C}.deref();
	Reference scriptTypes = Reference{&sec, 0x30}.deref();
	auto numTables       = Reference{&sec, 0x3C}.access<uint16_t>();
	Reference tableTable = Reference{&sec, 0x44}.deref();
	Reference typeImports = Reference{&sec, 0x48}.deref();

	os << "Section #" << sec.index << " (" << sec.header.id << ")";

	if (false) {
		Reference r{&sec, 0};
		pdump32(os, r, " ", 0, 20);
	}

	os << " (" << numTables << ") " << name << " : " << path;
	os << std::endl;

	os << " Parent: ";
	scriptTypeOneline(os, sec.ref().deref(0x18));
	//printref(os, Reference{&sec, 0x18}.deref());
	os << std::endl;

	auto scriptConfig = sec.ref().deref(0x34);
	if (scriptConfig.section == nullptr) {
		os << " No signatures" << std::endl;
	} else {
		os << " Signatures:" << std::endl;
		auto count = scriptConfig.access<uint32_t>(-4);
		for (unsigned i=0; i<count; scriptConfig.offset += 0x1C, i++) {
			os << "  ";
			dumpSignature(os, scriptConfig);
			os << std::endl;
		}
	}


	Reference nativeFuncRef {&sec, 0x38};
	nativeFuncRef = nativeFuncRef.deref();

	std::map<uint16_t, uint16_t> membersNames;

	if (scriptInit.section == nullptr) {
		os << " No script init" << std::endl;
	} else {
		os << " Script init:" << std::endl;
		auto count = scriptInit.access<uint32_t>(-4);
		for (unsigned i=0; i<count; scriptInit.offset += 0x14, i++) {
			membersNames[scriptInit.access<uint16_t>(12)] = scriptInit.access<uint16_t>(14);
			dumpInit(os, "  ", scriptInit, false);
		}
	}


	if (scriptTypes.section == nullptr) {
		os << " No member type info" << std::endl;
	} else {
		os << " Member types:" << std::endl;
		auto count = scriptTypes.access<uint32_t>(-4);
		for (unsigned i=0; i<count; i++) {
			auto pos = i*8;
			auto scriptType = scriptTypes.deref(pos);
			auto target = scriptTypes.access<uint32_t>(pos+4);
			os << "  this+" << target << ": ";
			if (scriptType.section == nullptr) {
				os << "unresolved" << std::endl;
			} else {
				scriptTypeOneline(os, scriptType);
				os << std::endl;
			}
		}
	}

	if (typeImports.section == nullptr) {
		os << " No type imports" << std::endl;
	} else {
		os << " Type imports:" << std::endl;
		auto count = typeImports.access<uint32_t>(-4);
		for (unsigned i=0; i<count; i++) {
			auto pos = i*4;
			auto scriptType = typeImports.deref(pos);
			if (scriptType.section == nullptr) {
				os << "  unresolved" << std::endl;
			} else {
				os << "  ";
				scriptTypeOneline(os, scriptType);
				os << std::endl;
			}
		}
	}
	if (nativeFuncRef.section == nullptr) {
		os << " Invalid main function table reference" << std::endl;
	} else {
		uint32_t numFuncs = nativeFuncRef.access<uint32_t>(-4);
		if (numFuncs == 0)
			os << " Empty main function table" << std::endl;
		else
			os << " Main table:" << std::endl;
		for (unsigned j=0; j<numFuncs; j++) {
			os << "  Function #" << sec.index << ".main." << j << std::endl;
			dumpFunction(os, nativeFuncRef, membersNames);
			nativeFuncRef.offset += 0x1C;
		}
	}

	if (tableTable.section == nullptr) {
		os << " No tables" << std::endl;
		/*Reference r{&sec, 0};
		dump32(os, r, " ", 0, 20);*/
		return;
	}

	for (uint32_t i=0; i<numTables; i++) {
		Reference table = tableTable.deref(i*4);
		auto numEntries = table.access<uint32_t>();
		os << " Table #" << sec.index << "." << i << " (" << numEntries << ")" << std::endl;

		for (uint32_t j=0; j<numEntries; j++) {
			os << "  Function #" << sec.index << "." << i << "." << j << std::endl;
			Reference func = table.deref(4+j*4);
			dumpFunction(os, func, membersNames);
		}
	}
}
