// gcc -g -std=c11 -Wall bigfuse.c `pkg-config fuse --cflags --libs` -o bigfuse

#define FUSE_USE_VERSION 26
#define _DEFAULT_SOURCE

#include <fuse.h>
#include <stdio.h>
#include <stdlib.h>
#define __USE_XOPEN_EXTENDED
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <assert.h>

#ifndef S_IFDIR
#define S_IFDIR 0x4000
#define S_IFREG 0x8000
#endif

static int bigf_getattr(const char *path, struct stat *stbuf);
static int bigf_readdir(const char *path, void *buf, fuse_fill_dir_t filler, off_t offset, struct fuse_file_info *fi);
static int bigf_open(const char *path, struct fuse_file_info *fi);
static int bigf_read(const char *path, char *buf, size_t size, off_t offset, struct fuse_file_info *fi);

static struct fuse_operations bigf_oper = {
	.getattr = bigf_getattr,
	.readdir = bigf_readdir,
	.open    = bigf_open,
	.read    = bigf_read,
};

static char *base;
static uint32_t *hashes;
static size_t num_hashes;
static uint32_t localeMask;
static size_t num_locale_matching_indices;
static size_t *locale_matching_indices;
static struct stat bigfile_stats[10];
static uint32_t chunk_size = 0x7FF00000;

static struct entry {
	uint32_t uncompressedSize;
	uint32_t offset;
	uint32_t locale;
	uint32_t compressedSize;
} *entries;

int sizes_pc[] = { /* for the bigfiles of DXHRDC */
	0x7febd000,
	0x7fa5d800,
	0x7fcac000,
	0x7fdfc800,
	0x7feed000,
	0x7feea000,
	0x7fe3a000,
	0x7fee0000,
	0x6c50b000,
	0
};

int sizes_mac_old[] = {
	0x7febc500,
	0x7fa32aa0,
	0x7fc90ee0,
	0x7fdd6450,
	0x7fed2dd0,
	0x7fec8590,
	0x7fe38470,
	0x7fede270,
	0x6c47a600,
	0
};

// file size based assumption
int sizes_mac_conservative[] = {
	0x7febd000,
	0x7fa5d800,
	0x7fcac000,
	0x7fdfc800,
	0x7feed000,
	0x7feea000,
	0x7fe3a000,
	0x7fee0000,
	0x6c50b000,
	0
};

// last file in bigfile based assumption
int sizes_mac_tight[] = {
	0x7febce94,
	0x7fa5d618,
	0x7fcabcc4,
	0x7fdfc520,
	0x7feec874,
	0x7fee9ee0,
	0x7fe39a4b,
	0x7fedff24,
	0x6c50adf2
};

int *sizes = sizes_mac_conservative;

static void bigfiles_mmap(char *bigpath) {
	size_t totalsize = 0;
	for (int i=0; sizes[i]; i++)
		totalsize += chunk_size; /*sizes[i];*/

	char *target = base = mmap(0, totalsize, PROT_READ, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	printf("first map gave %010lx\n", (size_t)target);
	bigpath = strdup(bigpath);
	char *numberPatchPoint = bigpath + strlen(bigpath) - 3;
	for (unsigned int i=0;; i++) {
		snprintf(numberPatchPoint, 4, "%03d", i);
		int fd = open(bigpath, O_RDONLY);
		if (fstat(fd, bigfile_stats+i))
			memset(bigfile_stats + i, 0, sizeof(struct stat));
		if (fd == -1)
			break;
		printf("Loaded bigfile[%03d]", i);
		if (target != mmap(target, sizes[i], PROT_READ, MAP_PRIVATE | MAP_FIXED, fd, 0)) {
			printf(": Couldn't get desired mmap\n");
			exit(1);
		}
		printf(" %010lx:%010lx:%010lx (%010x+%010x)\n",
			(uintptr_t)target,
			(uintptr_t)target+sizes[i],
			(uintptr_t)target+chunk_size,
			sizes[i],
			chunk_size-sizes[i]);
		target += chunk_size; /*sizes[i];*/
	}

	hashes = (uint32_t*)(base+8+64);
	num_hashes = hashes[-1];
	entries = (struct entry*)(hashes + num_hashes);
	//num_hashes = 100;

	// filter

	num_locale_matching_indices = 0;
	for (unsigned index=0; index < num_hashes; index++) {
		//printf("locale test %5d %08x %s\n", index, entries[index].locale,
		//	(entries[index].locale & localeMask) == localeMask ? "ok" : "fail");
		if ((entries[index].locale & localeMask) == localeMask)
			num_locale_matching_indices++;
	}

	locale_matching_indices = malloc(sizeof(size_t)*num_locale_matching_indices);
	size_t *nm = locale_matching_indices;
	for (unsigned index=0; index < num_hashes; index++) {
		{
			// bounds check
			uint64_t offset = entries[index].offset * 2048ul;
			unsigned filenr = offset / chunk_size;
			if ((offset % chunk_size) + entries[index].uncompressedSize > sizes[filenr]) {
				printf("file %08x index %08x wants abs range %10lx-%10lx rel range %10lx-%10lx in file[%d] of len %08x\n",
					hashes[index], index,
					offset, offset + entries[index].uncompressedSize,
					offset%chunk_size, offset%chunk_size + entries[index].uncompressedSize,
					filenr, sizes[filenr]);
			}
		}

		if ((entries[index].locale & localeMask) == localeMask)
			*nm++ = index;
	}
	assert (nm - locale_matching_indices == num_locale_matching_indices);
}

static uint32_t parsePath(const char *path) {
	uint32_t hash;
	if (sscanf(path, "/%x", &hash) != 1) return 0;
	return hash;
}

static uint32_t parseDword(const char *path) {
	uint32_t hash;
	if (sscanf(path, "%x", &hash) != 1) return 0;
	return hash;
}

static int compareUint32(const void *m1, const void *m2) {
	uint32_t mi1 = *(uint32_t*) m1;
	uint32_t mi2 = *(uint32_t*) m2;
	if (mi1 < mi2) return -1;
	if (mi1 > mi2) return  1;
	return 0;
}

static int indexForPath(const char *path) {
	uint32_t hash = parsePath(path);
	uint32_t *found = bsearch(&hash, hashes, num_hashes, sizeof(uint32_t), compareUint32);
	if (!found)
		return num_hashes;

	size_t index = found - hashes;
	while (index > 0 && hashes[index-1] == hash) index--;
	for (; hashes[index] == hash; index++)
		if ((entries[index].locale & localeMask) == localeMask)
			return index;

	return num_hashes;
}

static int bigf_getattr(const char *path, struct stat *stbuf)
{
	int res = 0;

	memset(stbuf, 0, sizeof(struct stat));
	if (strcmp(path, "/") == 0) {
		stbuf->st_mode = S_IFDIR | 0755;
		stbuf->st_nlink = 2;
	} else {
		size_t index = indexForPath(path);
		if (index >= num_hashes)
			return -ENOENT;

		stbuf->st_mode = S_IFREG | 0444;
		stbuf->st_nlink = 1;
		stbuf->st_size = entries[index].uncompressedSize;

		uint64_t offset = entries[index].offset * 2048ul;
		unsigned filenr = offset / chunk_size;

		stbuf->st_atime = bigfile_stats[filenr].st_atime;
		stbuf->st_mtime = bigfile_stats[filenr].st_mtime;
		stbuf->st_ctime = bigfile_stats[filenr].st_ctime;
	}

	return res;
}

static int bigf_readdir(const char *path, void *buf, fuse_fill_dir_t filler,
			 off_t offset, struct fuse_file_info *fi)
{
	(void) fi;

	if (strcmp(path, "/") != 0)
		return -ENOENT;

	#if 1
	switch (offset) {
	case 0: if (filler(buf, "." , NULL, 0 /*1*/)) return 0;
	case 1: if (filler(buf, "..", NULL, 0 /*2*/)) return 0; offset = 2;
	default: break;
	}
	for (unsigned i=0; i < num_hashes; i++) {
		if ((entries[i].locale & localeMask) != localeMask)
			continue;
	#else
	switch (offset) {
	case 0: if (filler(buf, "." , NULL, 1)) return 0;
	case 1: if (filler(buf, "..", NULL, 2)) return 0;
	default: break;
	}
	for (unsigned i=offset-2; i < num_locale_matching_indices; i++) {
	#endif
		char path[9];
		sprintf(path, "%08x", hashes[i]);
		if (filler(buf, path, NULL, 0))
			break;
		//sprintf(path, "%08x", hashes[locale_matching_indices[i]]);
		//if (filler(buf, path, NULL, 3+i))
		//	break;
	}

	return 0;
}

static int bigf_open(const char *path, struct fuse_file_info *fi)
{
	size_t index = indexForPath(path);
	if (index >= num_hashes)
		return -ENOENT;

	if ((fi->flags & 3) != O_RDONLY)
		return -EACCES;

	return 0;
}

static int bigf_read(const char *path, char *buf, size_t size, off_t offset2,
		      struct fuse_file_info *fi)
{
	size_t len;
	(void) fi;

	size_t index = indexForPath(path);
	if (index >= num_hashes)
		return -ENOENT;

	len = entries[index].uncompressedSize;
	if (offset2 < len) {
		if (offset2 + size > len)
			size = len - offset2;

		uint64_t offset = entries[index].offset * 2048ul;
		unsigned filenr = offset / chunk_size;
		assert((offset % chunk_size) + len <= sizes[filenr]);
		memcpy(buf, base + offset + offset2, size);
	} else
		size = 0;

	return size;
}

int main(int argc, char *argv[]) {
	if (argc < 3) {
		fprintf(stderr, "Usage: %s bigfile locale mountpoint fuseopts... "
			"(locale is a bitmask like BFFF0001)\n", argc ? argv[0] : "bigfuse");
		return 1;
	}
	bigfiles_mmap(argv[1]);
	localeMask = parseDword(argv[2]);
	argv[2] = argv[0];
	return fuse_main(argc-2, argv+2, &bigf_oper, NULL);
}
