def convert_pcd9(data: bytes):
    """ adapted from https://github.com/drewcassidy/quicktex/blob/main/quicktex/dds.py """
    import struct

    assert data[0:4] == b"\x50\x43\x44\x39"
    pcd9, tex_fmt, len_data, unknownC, img_width, img_height, img_depth, \
        unknown16, num_mipmaps, flags, tex_class = struct.unpack_from("<LLLLHHHBBHB", data)

    #print(pcd9, tex_fmt, len_data, unknownC, img_width, img_height, img_depth, \
    #    unknown16, num_mipmaps, flags, tex_class)

    # tex_class = 0   Unknown
    # tex_class = 1   2D
    # tex_class = 2   3D
    # tex_class = 3   Cube
    # tex_class = 4   NormalMap
    # flag 0x8000 also represents cubemap

    is_dxt = tex_fmt in (0x31545844, 0x33545844, 0x35545844)

    out_blob = b''

    # dds header
    out_blob += b'\x44\x44\x53\x20'

    def flags():
        caps = 0x1
        height = 0x2
        width = 0x4
        pitch = 0x8
        pixel_format = 0x1000
        mipmap_count = 0x20000
        linear_size = 0x80000

        out = caps | height | width | pixel_format
        if is_dxt:
            out |= linear_size
        else:
            out |= pitch
        if num_mipmaps > 0:
            out |= mipmap_count

        return out


    def pitch():
        cols = (img_width + 3) // 4
        rows = (img_height + 3) // 4

        if tex_fmt == 21:
            return int(4 * img_width) # don't multiply with img_height
        elif tex_fmt == 827611204: # DXT1
            blk_size = 8
        elif tex_fmt == 861165636 or tex_fmt == 894720068: # DXT3 DXT5
            blk_size = 16
        else:
            assert False, "unknown tex format: {:x}".format(tex_fmt)

        return int(rows * cols * blk_size)

    out_blob += struct.pack(
        '<7I44x',
        124,  # length of dds header
        flags(),
        img_height,
        img_width,
        pitch(),
        0,  # depth,
        num_mipmaps,
    )

    def pixel_format():
        flags_alpha_pixels = 0x1
        flags_fourcc = 0x4
        flags_rgb = 0x40

        if tex_fmt == 21:
            return flags_rgb | flags_alpha_pixels
        else:
            return flags_fourcc

    fourcc = 0 if tex_fmt == 21 else tex_fmt
    pixel_size = 32 if tex_fmt == 21 else 0
    pixel_bitmasks = (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000) if tex_fmt == 21 else (0, 0, 0, 0)

    out_blob += struct.pack(
        '<8I',
        32,
        pixel_format(),
        fourcc,
        pixel_size,
        *pixel_bitmasks
    )

    def dwCaps1():
        flags_complex = 0x8
        flags_mipmap = 0x400000
        flags_texture = 0x1000

        out = flags_texture
        if num_mipmaps > 0:
            out |= (flags_complex | flags_mipmap)
        return out

    def dwCaps2():
        # flags_fullcubemap = 0xFE00
        # if tex_class == 3:
        #     return flags_fullcubemap

        return 0

    out_blob += struct.pack(
        '<4I4x',
        dwCaps1(),  # dwCaps1
        dwCaps2(),  # dwCaps2
        0,  # dwCaps3 = 0
        0   # dwCaps4 = 0
    )

    assert len(out_blob) == 124 + 4

    out_blob += data[28:]
    
    return img_width, img_height, out_blob
