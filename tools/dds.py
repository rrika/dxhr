def convert_pcd9(data: bytes):
    """ adapted from https://github.com/drewcassidy/quicktex/blob/main/quicktex/dds.py """
    import struct

    assert data[0:4] == b"\x50\x43\x44\x39"
    pcd9, tex_fmt, len_data, len_mipmaps, img_width, img_height, _, _ = struct.unpack_from("LLLLHHLL", data)

    out_blob = b''

    # dds header
    out_blob += b'\x44\x44\x53\x20'

    def flags():
        caps = 0x1
        height = 0x2
        width = 0x4
        pixel_format = 0x1000
        mipmap_count = 0x20000
        linear_size = 0x80000

        out = caps | height | width | pixel_format | linear_size
        if len_mipmaps > 0:
            out |= mipmap_count

        return out


    def pitch():
        rows = max([1, int((img_height + 3) / 4)])
        cols = max([1, int((img_width + 3) / 4)])

        if tex_fmt == 21:
            return int(4 * img_height * img_width)
        if tex_fmt == 827611204:
            blk_size = 8
        if tex_fmt == 861165636 or tex_fmt == 894720068:
            blk_size = 16
        return int(rows * cols * blk_size)

    out_blob += struct.pack(
        '<7I44x',
        124,  # length of dds header
        flags(),
        img_height,
        img_width,
        pitch(),
        0,  # depth,
        len_mipmaps,
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
        if len_mipmaps > 0:
            out |= (flags_complex | flags_mipmap)
        return out

    out_blob += struct.pack(
        '<4I4x',
        dwCaps1(),  # dwCaps1
        0,  # dwCaps2 - no cubemaps in DXHR... technically.
        0,  # dwCaps3 = 0
        0  # dwCaps4 = 0
    )

    assert len(out_blob) == 124 + 4

    out_blob = data[28:]
    
    return img_height, img_height, out_blob
