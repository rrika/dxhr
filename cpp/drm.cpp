#include <iostream>
#include <stdexcept>
#include <cstring>
#include "drm.h"
#include "zlib.h"

extern "C" size_t strlen(const char*);

namespace DRM {

	static uint32_t magicCompressed = 0x4D524443;

	static inline uint64_t align16(uint64_t value) { return (value+15)&~15; }

	const char *sectionTypeName(Section::ContentType ct) {
		const char *names[] = {
			"Generic",
			"Empty",
			"Animation",
			nullptr,
			nullptr, // 4
			"RenderResource",
			"FMODSoundBank",
			"DTPData",
			"Script", // 8
			"ShaderLib",
			"Material",
			"Object",
			"RenderMesh", // 12
			"CollisionMesh",
			"StreamGroupList"
		};
		return names[unsigned(ct)];
	}

	std::ostream & operator<<(std::ostream &os, const Section::Reference& ref) {
		return os << "(" << ref.section->index << ": " << ref.offset << ")";
	}

	struct Fixer {
		Database& db;
		DRM& drm;
		Section& section;
		typedef Section::Reference Reference;

		void fixup0(uint64_t value) {
			Reference patchSite{&section, static_cast<uint32_t>(value)};
			Reference target   {&section, static_cast<uint32_t>(value >> 32)};
			//std::cerr << patchSite << " = &" << target << std::endl;
			section.fixups[patchSite.offset] = target;
		}

		void fixup1(uint64_t value) {
			Reference patchSite{&section,                static_cast<uint32_t>((value & 0x0000003FFFFFC000) >> 12)}; // instead of >> 14
			Reference target   {&drm.at(value & 0x3FFF), static_cast<uint32_t>((value & 0xFFFFFFC000000000) >> 38)};
			//std::cerr << patchSite << " = &" << target << std::endl;
			section.fixups[patchSite.offset] = target;
		}

		void fixup2(uint32_t value) {
			uint32_t offset = (value & 0x01FFFFFF)*4;
			Reference patchSite{&section, offset};

			auto referencedId = patchSite.access<uint32_t>();
			auto referencedType = Section::ContentType((value & 0xFE000000) >> 25);

			auto it = db.objects.find(Database::key(referencedType, referencedId));
			if (it != db.objects.end()) {
				Section& tSection = *it->second;
				Reference rTarget{&tSection, 0};
				section.fixups[offset] = rTarget;
			} else {
				section.fixups[offset] = Reference{nullptr, 0};
			}
		}

		void fixup3(uint32_t value) {
			throw std::runtime_error("can't handle type 3 at this point");
		}

		void fixup4(uint32_t value) {
			// like fixup2 but wrapped
			uint32_t offset = (value & 0x01FFFFFF)*4;
			Reference patchSite{&section, offset};

			auto referencedId = patchSite.access<uint32_t>();
			auto referencedType = Section::ContentType((value & 0xFE000000) >> 25);

			auto it = db.objects.find(Database::key(referencedType, referencedId));
			if (it != db.objects.end()) {
				Section& tSection = *it->second;
				Reference rTarget{&tSection, 0};
				section.fixups[offset] = rTarget;
			} else {
				section.fixups[offset] = Reference{nullptr, 0};
			}
		}
	};

	void dumpFixups(std::ostream &os, Section& section) {
		for (auto p: section.fixups) {
			if (p.second.section)
				os << p.first << " -> (" << p.second.section->index << ": " << p.second.offset << ")" << std::endl;
		}
	}

	Data decompress(Data& input) {

		// std::cout << std::hex;
		// std::cerr << std::hex;

		if (input.size() < 16)
			throw std::runtime_error("CDRM: incomplete header");

		struct CDRMHeader {
			uint32_t magic;
			uint32_t version;
			uint32_t count;
			uint32_t padding;
			struct {
				uint32_t uncompressedSizeAndType;
				uint32_t compressedSize;
			} index[];
		} *header = (CDRMHeader*) input.data();

		auto startOfPayload = align16(16 + header->count * 8);

		if (header->magic != magicCompressed)
			throw std::runtime_error("CDRM: magic value not found");
		if (header->version != 2)
			throw std::runtime_error("CDRM: unsupported version");
		if (startOfPayload != (16 + header->count * 8 + header->padding))
			throw std::runtime_error("CDRM: precomputed padding wrong");
		if (input.size() < startOfPayload)
			throw std::runtime_error("CDRM: incomplete index");

		uint32_t totalPayload = 0;
		uint32_t totalCompressedPayload = 0;
		for (auto i=0u; i<header->count; i++) {
			auto& entry = header->index[i];
			totalPayload           = align16(totalPayload) + (entry.uncompressedSizeAndType >> 8);
			totalCompressedPayload = align16(totalCompressedPayload) + entry.compressedSize;
		}

		if (input.size() < startOfPayload+totalCompressedPayload)
			throw std::runtime_error("CDRM: truncated payload");

		Data output(totalPayload);

		uint32_t inCursor  = startOfPayload;
		uint32_t outCursor = 0;

		for (uint32_t i=0; i<header->count; i++) {

			auto& entry = header->index[i];
			uint32_t uncompressedSize = entry.uncompressedSizeAndType >> 8;
			uint8_t  type             = entry.uncompressedSizeAndType;
			uint32_t compressedSize   = entry.compressedSize;

			uint8_t *target = output.data() + outCursor;
			uint8_t *source =  input.data() +  inCursor;
			inCursor  += align16(compressedSize);
			outCursor += align16(uncompressedSize);

			if (type == 1) {
				if (uncompressedSize != compressedSize)
					throw std::runtime_error("CDRM: malformed raw-block");
				memcpy(target, source, uncompressedSize);
			} else if (type == 2) {
				uint64_t actualUncompressedSize = uncompressedSize;
				if (uncompress(target, &actualUncompressedSize,
				               source, compressedSize) != 0 ||
				    actualUncompressedSize != uncompressedSize
				)
					throw std::runtime_error("CDRM: malformed zlib-block");
			} else {
				std::cerr << (unsigned)type << std::endl;
				throw std::runtime_error("CDRM: unknown block-type");
			}
		}

		return output;
	}

	DRM* fromBuffer(Data& data, std::string origin, std::vector<std::string>& fileDependencies) {
		auto magic = *(uint32_t*)&data.at(0);

		if (magic == magicCompressed) {
			Data uncompressed = decompress(data);
			data.swap(uncompressed);
		}

		struct ArchiveHeader {
			uint32_t version;
			uint32_t dependencyListSize;
			uint32_t unknown08_size;
			uint32_t unknown0C;
			uint32_t unknown10;
			uint32_t flags;
			uint32_t sectionCount;
			uint32_t rootSection;
			struct Section::Header sectionHeaders[];
		} *header = (ArchiveHeader*) data.data();

		bool realign = header->flags & 1;
		// std::cerr << "realign is " << realign << std::endl;
		// std::cerr << "rootSection is " << header->rootSection << std::endl;
		auto& sHeaders = header->sectionHeaders;

		if (header->version != 21)
			throw std::runtime_error("DRM: only version 21 (0x15) is supported");
		if (header->unknown0C != 0)
			throw std::runtime_error("DRM: header[0xC] != 0");

		uint32_t cursor = (sizeof(ArchiveHeader)+sizeof(Section::Header)*header->sectionCount);

		auto blob08         = cursor; cursor += header->unknown08_size;
		auto dependencyList = cursor; cursor += header->dependencyListSize;

		(void)blob08;

		if (realign) cursor = align16(cursor);

		std::shared_ptr<Data> shData(&data);

		for (uint32_t cursor=0; cursor<header->dependencyListSize;) {
			const char *name = (const char*)data.data() + dependencyList + cursor;
			fileDependencies.emplace_back(name);
			cursor += strlen(name) + 1;
		}

		DRM& drm = * new DRM(header->sectionCount);
		for (uint32_t i=0; i<header->sectionCount; i++) {
			auto& section = drm[i];

			section.index = i;
			section.isRoot = (i == header->rootSection);
			section.header = sHeaders[i];
			section.keepDataAlive = shData;
			section.origin = origin;

			if (cursor >= data.size())
				throw std::runtime_error("drm inconsistency");

			section.fixupCursor = cursor; cursor += (section.header.fixupSizeAndflags>>8);
			if (realign) cursor = align16(cursor);
			section.payloadCursor = cursor; cursor += (section.header.payloadSize);
			if (realign) cursor = align16(cursor);

			/*std::cerr << "section #" << i << ": " << sectionTypeName(section.header.type) << " (" << section.header.id;
			if (section.isRoot)
				std::cerr << "; ROOT";
			std::cerr << ")" << std::endl;*/
		}

		return &drm;
	}

	DRM* fromBuffer(Data& data, std::string origin) {
		std::vector<std::string> _;
		return fromBuffer(data, origin, _);
	}

	void applyFixup(Database& db, DRM& drm) {
		for (uint32_t i=0; i<drm.size(); i++) {
			auto& section = drm[i];
			auto& data = *section.keepDataAlive;

			// std::cerr << "section #" << i << " " << section.header.id << ": " << sectionTypeName(section.header.type) << std::endl;

			if ((section.header.fixupSizeAndflags >> 8) == 0)
				continue;

			struct FixupHeader {
				uint32_t count0;
				uint32_t count1;
				uint32_t count2;
				uint32_t count3;
				uint32_t count4;
			} *fixupHeader = (FixupHeader*)&data.at(section.fixupCursor);

			if (0)
				std::cerr << fixupHeader->count0 << " "
				          << fixupHeader->count1 << " "
				          << fixupHeader->count2 << " "
				          << fixupHeader->count3 << " "
				          << fixupHeader->count4 << std::endl;

			uint32_t subCursor = section.fixupCursor+sizeof(FixupHeader);

			Fixer fixer{db, drm, section};

			uint64_t* fRaw0 = (uint64_t*)&data.at(subCursor);
			for (uint32_t i=0; i<fixupHeader->count0; i++, subCursor += 8)
				fixer.fixup0(fRaw0[i]);

			uint64_t* fRaw1 = (uint64_t*)&data.at(subCursor);
			for (uint32_t i=0; i<fixupHeader->count1; i++, subCursor += 8)
				fixer.fixup1(fRaw1[i]);

			uint32_t* fRaw2 = (uint32_t*)&data.at(subCursor);
			for (uint32_t i=0; i<fixupHeader->count2; i++, subCursor += 4)
				fixer.fixup2(fRaw2[i]);

			uint32_t* fRaw3 = (uint32_t*)&data.at(subCursor);
			for (uint32_t i=0; i<fixupHeader->count3; i++, subCursor += 4)
				fixer.fixup3(fRaw3[i]);

			uint32_t* fRaw4 = (uint32_t*)&data.at(subCursor);
			for (uint32_t i=0; i<fixupHeader->count4; i++, subCursor += 4)
				fixer.fixup4(fRaw4[i]);

		}
	}

	/*void Database::MetaData::arrive(Database& db) {
		for (auto& section: sections) {
			db.objects[Database::key(section)] = &section;
		}
		for (auto* f: supply) {
			if (--f->numPending)
				continue;
			f->arrive(db);
		}
	}

	void Database::MetaData::need(Database::MetaData& other) {
		depend.push_back(other);
		other.supply.push_back(this);
		if (other.present)
			numPending++;
	}*/

	Database::~Database() {
		for (auto& p: files) {
			delete p.second.sections;
		}
	}

	Database::MetaData& Database::load(std::string& fname, Data* (*read)(std::string&)) {
		auto& meta = files[fname];

		if (meta.sections)
			return meta;

		std::vector<std::string> fileDependencies;
		Data* data;
		try {
			data = read(fname);
		} catch(std::runtime_error& e) {
			return meta;
		}
		meta.sections = fromBuffer(*data, fname, fileDependencies);
		for (auto& dep: fileDependencies) {
			load(dep, read);
		}
		for (auto& section: *meta.sections) {
			objects[Database::key(section)] = &section;
		}
		applyFixup(*this, *meta.sections);
		return meta;
	}
}
