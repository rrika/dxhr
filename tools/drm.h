#pragma once

#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace DRM {

	typedef std::vector<uint8_t> Data;

	struct Section {
		struct Reference {
			Section* section;
			uint32_t offset;
			void valid() {
				if (section == nullptr)
					throw std::runtime_error("Reference::section == nullptr");

			}
			void out_of_range(uint32_t x) {
				std::stringstream ss;
				ss << std::hex;
				ss << x << "/" << section->header.payloadSize;
				throw std::out_of_range(ss.str());
			}
			template <class T> inline T& access(uint32_t x=0) {
				valid();
				x += offset;
				if (x+sizeof(T) > section->header.payloadSize)
					out_of_range(x);
				return *(T*)(&section->keepDataAlive->at(section->payloadCursor+x));
			}
			Reference deref(uint32_t x=0) {
				valid();
				x += offset;
				if (x+sizeof(uint32_t) > section->header.payloadSize)
					out_of_range(x);
				return section->fixups[x];
			}
			inline bool operator==(const Reference& other) const {
				return section == other.section && offset == other.offset;
			}
		};
		enum class ContentType : uint8_t {
			Generic = 0,
			Empty = 1,
			Animation = 2,
			RenderResource = 5,
			FMODSoundBank = 6,
			DTPData = 7,
			Script = 8,
			ShaderLib = 9,
			Material = 10,
			Object = 11,
			RenderMesh = 12,
			CollisionMesh = 13,
			StreamGroupList = 14
		};
		struct Header {
			uint32_t payloadSize;
			ContentType type;
			uint8_t  unknown05;
			uint16_t unknown06;
			uint32_t fixupSizeAndflags;
			/* (fixupSizeAndflags >> 1) & 0x7f
			   = 5  texture
			   = 24 terrain
			   = 26 model
			   = 27 nothing
			*/
			uint32_t id;
			uint32_t languageBits;
			/* languageBits & 0x80000000 -> direct x 11 compatible
			   languageBits & 0x40000000 -> direct x  9 compatible */
		};
		inline bool operator==(const Section& other) const {
			return this == &other;
		}
		inline Reference ref() { return Reference{this, 0}; }

		Header header;
		uint16_t index;
		bool     isRoot;
		uint32_t fixupCursor;
		uint32_t payloadCursor;
        std::map<uint32_t, Reference> fixups;
    	std::shared_ptr<Data> keepDataAlive;
    	std::string origin;
	};

	typedef std::vector<Section> DRM;

	struct Database {
		struct MetaData {
			DRM *sections;
			Section::Reference rootRef;
		};
		std::map<uint32_t, Section*> objects;
		std::map<std::string, MetaData> files;

		~Database();

		Database::MetaData& load(std::string& fname, Data* (*read)(std::string&));
		static inline uint32_t key(Section::ContentType type, uint16_t id) {
			return uint8_t(type) + (id << 8);
		}
		static inline uint32_t key(Section& section) {
			return key(section.header.type, section.header.id);
		}
	};

	const char *sectionTypeName(Section::ContentType ct);

	void dumpFixups(std::ostream &os, Section& section);
	Data decompress(Data& data);
	DRM* fromBuffer(Data& data, std::string origin, std::vector<std::string>& fileDependencies);
	DRM* fromBuffer(Data& data, std::string origin);
	void applyFixup(DRM& drm);
}
