#pragma once

#include <iostream>
#include "drm.h"

void scriptReport(std::ostream &os, DRM::DRM& drm);
void scriptReportS(std::ostream &os, DRM::Section& sec);

struct StringTable {
	std::vector<uint32_t> data;
	std::string operator[] (size_t i) const {
		if (i < 3)
			return "(null)";
		if (i+1 >= data.size())
			return "(out-of-bounds)";
		size_t a = data[i+2];
		size_t b = data[i+3];
		auto s = (char*)data.data();
		return {s+a, s+b};
	}
};

extern StringTable stringtable;
