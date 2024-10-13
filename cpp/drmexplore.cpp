#include <fstream>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <unordered_map>
#include <set>
#include <sstream>
#include <cctype>
#include "drm.h"
#include "script.h"

using Reference = DRM::Section::Reference;
using Section = DRM::Section;

std::unordered_map<uint32_t, std::string> dtpPaths;

template <class T>
struct ll {
	ll<T> *n;
	T& r;
	inline bool foundRecursion() {
		for (auto* u=n; u; u=u->n)
			if (u->r == r)
				return true;

		return false;
	}
};

void printref(std::ostream &os, Reference r) {
	if (r.section != nullptr)
		os << "(" << r.section->origin << "/" << r.section->index << "." << DRM::sectionTypeName(r.section->header.type) << ": " << r.offset << ")";
	else
		os << "(null)";
}

static void dump32(std::ostream &os, Reference& data, std::string indent, int32_t start, int32_t count, ll<Reference>* l=nullptr) {

	ll<Reference> v{l, data};

	if (v.foundRecursion()) {
		os << indent << "recursion detected" << std::endl;
		return;
	}

	if (start < 0)
		start = 0;

	for (int32_t i=start; i<count; i++) {
		uint32_t item;

		if (data.offset + i*4 + sizeof(uint32_t) > data.section->header.payloadSize)
			break;

		item = data.access<uint32_t>(i*4);

		os << indent << std::setfill('0') << std::setw(4) << data.offset+i*4 << ": " << std::setw(8) << item << std::setw(0);
		Reference r = data.deref(i*4);
		if (r.section == nullptr) {
			auto ps = [](char c) { return isprint(c) ? c : '.'; };
			os << " "
				<< ps(data.access<char>(i*4+0))
				<< ps(data.access<char>(i*4+1))
				<< ps(data.access<char>(i*4+2))
				<< ps(data.access<char>(i*4+3));
			if (item == 0xbeebbeeb)
				os << " no ref though";
		} else {
			os << " -> ";
			printref(os, r);
			os << std::endl;
			bool skip = (data.section == r.section &&
				r.offset < data.offset + count*4 &&
				r.offset < data.offset + i*4 + 16);
			if (!skip)
				dump32(os, r, indent+"  ", -1, 4, &v);
		}
		os << std::endl;
	}
}

void pdump32(std::ostream &os, Reference& data, std::string indent, int32_t start, int32_t count) {
	dump32(os, data, indent, start, count);
}

static void summary(std::ostream &os, Section& s) {

	unsigned dxflags = s.header.languageBits >> 30;
	const char *levels[] = {" DX?", " DX9", " DX11", ""};

	os << s.origin << "/" << s.index << ": ";

	os << DRM::sectionTypeName(s.header.type);

	switch (uint8_t st = (s.header.fixupSizeAndflags >> 1) & 0x7f) {
		case 5:  os << " (Texture)"; break;
		case 13: os << " (Sound)"; break;
		case 24: os << " (RenderTerrain)"; break;
		case 26: os << " (RenderModel)"; break;
		case 27: os << " (?)"; break;
		case 40: os << " (SmartScript)"; break;
		case 41: os << " (Scaleform)"; break;
		case 42: os << " (Conversation)"; break;
		case 50: os << " (CameraShake)"; break;
		default: os << " " << (int)st;
	}

	os << " " << s.header.id;
	if (s.header.type == Section::ContentType::Script) {
		os << " ";
		void scriptTypeName(std::ostream &os, Reference scriptType);
		scriptTypeName(os, s.ref());
	} else if (s.header.type == Section::ContentType::FMODSoundBank) {
		os << " ";
		Reference fmod{&s, 16};
		auto numFiles = fmod.access<uint32_t>(4);
		fmod.offset += 48;
		for (auto i=0u; i<numFiles; i++)
		{
			uint16_t size = fmod.access<uint16_t>(0);
			char *nameBegin = &(fmod.access<char>(2));
			char *nameEnd = &(fmod.access<char>(32));
			std::string name(nameBegin, nameEnd);
			if (i)
				os << ",";
			os << name;
			fmod.offset += size;
		}
	}
	os << " unk6:" << s.header.unknown06
	   << levels[dxflags]
	   << " (" << s.header.payloadSize << " bytes)";

	if (s.header.type == Section::ContentType::DTPData ||
	    s.header.type == Section::ContentType::RenderMesh ||
	    s.header.type == Section::ContentType::Material ||
	    s.header.type == Section::ContentType::Script)
		if (auto pathIt = dtpPaths.find(s.header.id); pathIt != dtpPaths.end())
			os << " " << pathIt->second;

	os << std::endl;
}

static void dumpS(
	std::ostream &os,
	Section& s,
	std::string indent,
	ll<Section>* l=nullptr)
{
	ll<Section> v{l, s};

	if (v.foundRecursion()) {
		os << indent << "..." << std::endl;
		return;
	}

	os << indent;
	summary(os, s);

	if (s.header.type == Section::ContentType::Material)
		//return
		;

	std::set<Section*> referencedSections;
	for (auto kv: s.fixups) {
		referencedSections.insert(kv.second.section);
	}
	for (auto* section: referencedSections) {
		if (section == nullptr) {
			os << indent << "?" << std::endl;
			continue;
		}
		dumpS(os, *section, indent+"  ", &v);
	}
}

DRM::Database db;
std::string basefolder;

void listFiles(DRM::Database& db){	
	for (auto kv: db.files) {
		std::cout << (kv.second.sections == nullptr ? "- " : "+ ") << kv.first << std::endl;
	}
}

static void query(DRM::DRM* drm, std::string q) {
	std::stringstream qs(q);
	char command;

	std::vector<Section*> domain;

	if (drm == nullptr)
		throw std::runtime_error("query(): drm must not be nullptr");

	while (true) {
		qs >> command;
		if (qs.eof())
			break;
		switch (command) {
			// Applies to whole DRM
			case 'd': { // dependencies
				listFiles(db);
				break;
			}

			// Select sections
			case 'n': { // specific number
				unsigned int index; qs >> index;
				auto& section = drm->at(index);
				domain.push_back(&section);
				break;
			}
			case 'q': { // root object
				for (auto& section: *drm) {
					if (section.isRoot)
						domain.push_back(&section);
				}
				break;
			}
			case 'a': { // all
				for (auto& section: *drm) {
					domain.push_back(&section);
				}
				break;
			}
			case 'x': { // all (extended)
				for (auto kv: db.files) {
					if (kv.second.sections == nullptr)
						continue;
					for (auto& section: *kv.second.sections) {
						domain.push_back(&section);
					}
				}
				break;
			}

			// Inspect selected sections
			case 'f': { // relocations
				for (auto* section: domain) {
					summary(std::cout, *section);
					dumpFixups(std::cout, *section);
				}
				break;
			}
			case 'w': { // print words with crossreferences
				for (auto* section: domain) {
					uint32_t size = section->header.payloadSize;
					Reference r{section, 0};
					dump32(std::cout, r, "", 0, size/4);
				}
				break;
			}
			case 'r': { // raw
				for (auto* section: domain) {
					std::cout.write((const char*)&(*(section->keepDataAlive))[section->payloadCursor], section->header.payloadSize);
				}
				break;
			}
			case 's': { // summary
				for (auto* section: domain)
					summary(std::cout, *section);
				break;
			}
			case 'h': { // hierarchical summary
				for (auto* section: domain) {
					dumpS(std::cout, *section, "");
				}
				break;
			}

			// Special cases
			case 'i': { // detail about scripts
				for (auto* section: domain) {
					summary(std::cout, *section);
					scriptReportS(std::cout, *section);
				}
				break;
			}
			default: break;
		}
	}
}

static DRM::Data *openFile(std::string& filename) {
	for (auto& c: filename)
		if (c == '\\') c = '/';

	std::ifstream in(basefolder+filename, std::ios::in | std::ios::binary);
	if (!in)
		throw std::runtime_error("couldn't load drm file");

	in.seekg(0, std::ios::end);
	auto *contents = new DRM::Data(in.tellg());
	in.seekg(0, std::ios::beg);
	in.read((char*)contents->data(), contents->size());
	in.close();
	return contents;
}

void load_dtpids() {
	std::string devfolder = basefolder;
	devfolder.resize(devfolder.size() - 3); // remove "-w/"
	devfolder += "-dev/";                   // add  "-dev/"
	std::ifstream in(devfolder+"/dtpdata.ids", std::ios::in | std::ios::binary);
	if (!in)
		return;

	{ uint32_t count; in >> count; }
	while (!in.eof()) {
		uint32_t index; in >> index;
		{ char comma; in >> comma; }

		std::string name;
		std::getline(in, name);
		if (name[name.size()-1] == '\r')
			name.resize(name.size() - 1);

		dtpPaths[index] = std::move(name);
	}

	in.close();
}

int main(int argc, char **argv) {
	if (argc < 4) {
		std::cerr << "Usage: drmexplore path/to/drms/ file.drm {query}" << std::endl;
		std::cerr << "Queries begin with selectors:" << std::endl;
		std::cerr << "  n10   only section 10" << std::endl;
		std::cerr << "  a     all sections of the file" << std::endl;
		std::cerr << "  x     all sections of the file and its dependencies" << std::endl;
		std::cerr << "  q     the root section of the file" << std::endl;
		std::cerr << "Followed by per-section actions:" << std::endl;
		std::cerr << "  f     print relocations" << std::endl;
		std::cerr << "  w     print hexwords" << std::endl;
		std::cerr << "  r     print raw contents" << std::endl;
		std::cerr << "  s     print one line summary" << std::endl;
		std::cerr << "  h     print tree of references" << std::endl;
		std::cerr << "Or global commands" << std::endl;
		std::cerr << "  d     list dependencies of the file" << std::endl;

		return 1;
	}

	std::cout << std::hex;

	basefolder = argv[1];
	std::string fname(argv[2]);
	auto handle = db.load(fname, openFile);
	load_dtpids();
	for (int i=3; i<argc; i++)
		query(handle.sections, std::string(argv[i]));

	return 0;
}
