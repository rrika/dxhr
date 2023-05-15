import drm
import bigfile

# two objects in the first scene of the game (megan's office)
matchbox_car_offset = 0x20c4b0
newspaper_offset = 0x20b870

basepath = "./pc-w"
db = drm.DB(basepath)
sections, rootsectionindex, extra = db.load("det_sarifhq_rail_tutorial.drm")
data = bytearray(sections[0].payload)

matchbox_car_position = data[matchbox_car_offset + 16 : matchbox_car_offset + 32]
newspaper_position = data[newspaper_offset + 16 : newspaper_offset + 32]

data[matchbox_car_offset + 16 : matchbox_car_offset + 32] = newspaper_position
data[newspaper_offset + 16 : newspaper_offset + 32] = matchbox_car_position

sections[0].payload = bytes(data)
modified_drm = extra.write(sections, rootsectionindex)
with open("swapper.000", "wb") as f:
	bigfile.write_bigfile(f, [
		(b"pc-w\\det_sarifhq_rail_tutorial.drm", 0xffffffff, modified_drm)
	])

# use with https://github.com/gibbed/DXHRDC-ModHook
