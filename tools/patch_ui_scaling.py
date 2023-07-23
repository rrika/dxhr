import drm
import bigfile
import struct

# use with https://github.com/gibbed/DXHRDC-ModHook

uint32 = struct.Struct("<I").unpack_from
f32x4 = struct.Struct("<ffff").unpack_from

basepath = "./pc-w"
db = drm.DB(basepath)
sections, rootsectionindex, extra = db.load("globalscaleformdatabase.drm")
r_obj = drm.Reference(sections, sections[rootsectionindex])
r_dtp = r_obj.deref(0)
r_data = r_dtp.deref(0xBC)
n_scaleform_movies, = r_data.access(uint32, 0)
r_dtp_movies = r_data.deref(4)

def build_patch(scale):
	def focus(x, y):
		return (x*(1-scale), y*(1-scale), scale, scale)

	top_left      = focus(0.0, 0.0)
	top_center    = focus(0.5, 0.0)
	top_right     = focus(1.0, 0.0)
	middle_left   = focus(0.0, 0.5)
	middle_center = focus(0.5, 0.5)
	middle_right  = focus(1.0, 0.5)
	bottom_left   = focus(0.0, 1.0)
	bottom_center = focus(0.5, 1.0)
	bottom_right  = focus(1.0, 1.0)

	patch = {
		# "scaleform\\OuterShell\\Cursor\\Cursor"
		# "scaleform\\OuterShell\\LetterBox\\LetterBox"
		# "scaleform\\outershell\\pausemenu\\pausemenu"
		# "scaleform\\outershell\\debugmenu\\debugmenu"
		# "scaleform\\outershell\\saveloadsystem\\saveloadsystem"
		# "scaleform\\outershell\\deathmenu\\deathmenu"
		# "scaleform\\outershell\\videosetup\\videosetup"
		# "scaleform\\OuterShell\\CinematicPauseMenu\\CinematicPauseMenu"
		# DUPLICATE "scaleform\\OuterShell\\CinematicPauseMenu\\CinematicPauseMenu"
		"scaleform\\inbrain\\hud\\hudelements\\subtitles\\subtitles": bottom_center, # doesn't seem to affect subtitles
		# "scaleform\\OuterShell\\CinematicCommentaryOverlay\\CinematicCommentaryOverlay"
		# "scaleform\\inbrain\\gamemenu\\menu\\gamemenu"
		# "scaleform\\inbrain\\gamemenu\\menusections\\augmentations\\augmentations"
		# "scaleform\\inbrain\\gamemenu\\menusections\\map\\gamemap"
		# "scaleform\\inbrain\\gamemenu\\menusections\\missionlog\\missionslog"
		# "scaleform\\inbrain\\gamemenu\\menusections\\inventory\\inventory"
		# "scaleform\\inbrain\\gamemenu\\menusections\\medialog\\medialog"
		"scaleform\\inbrain\\hud\\hudcontroller\\hudcontroller": None, # unsure what this does
		"scaleform\\inbrain\\hud\\hudelements\\healthbar\\healthbar": top_left,
		# "scaleform\\inbrain\\hud\\hudelements\\lootselector\\lootselector"
		"scaleform\\inbrain\\hud\\hudelements\\briefer\\briefer": top_right, # doesn't seem to affect radio comms UI
		# "scaleform\\inbrain\\hud\\hudelements\\dialog\\socialaugmentation\\socialaug"
		# "scaleform\\inbrain\\hud\\hudelements\\dialog\\dialogsystem\\dialogsystem"
		# "scaleform\\inbrain\\hud\\hudelements\\damageindicator\\damageindicator"
		# "scaleform\\InBrain\\HUD\\HUDElements\\QuickInventory\\QuickInventory"
		"scaleform\\inbrain\\hud\\hudelements\\reticles\\reticles": middle_center,
		"scaleform\\inbrain\\hud\\hudelements\\weaponindicator\\weaponindicator2": bottom_right,
		"scaleform\\inbrain\\hud\\hudelements\\selectionbox\\selectionbox": None,
		"scaleform\\inbrain\\hud\\hudelements\\logger\\logger": None, # this does messages on the left and XP updates on the right, can't see both at the same time
		"scaleform\\inbrain\\hud\\hudelements\\radar\\radar": bottom_left,
		# "scaleform\\inbrain\\hud\\hudelements\\codecollector\\codecollector"
		# "scaleform\\inbrain\\hud\\hudelements\\menuwheel\\menuwheel"
		# "scaleform\\inbrain\\hud\\hudelements\\misc\\arrow_top"
		# "scaleform\\inbrain\\hud\\hudelements\\misc\\object_sensor"
		"scaleform\\inbrain\\hud\\hudelements\\augmentationsbars\\augmentationbars": None,
		# DUPLICATE "scaleform\\inbrain\\hud\\hudelements\\subtitles\\subtitles"
		# "scaleform\\InBrain\\HUD\\HUDElements\\Dialog\\PersonalityType\\PersonalityType"
		"scaleform\\InBrain\\HUD\\HUDElements\\StealthEnhancer\\StealthEnhancer": None,
		"scaleform\\InBrain\\HUD\\HUDElements\\ScreenMarking\\ScreenMarking": None,
		# "scaleform\\InBrain\\HUD\\HUDElements\\SelectionBoxMinimal\\SelectionBox"
		"scaleform\\InBrain\\HUD\\HUDElements\\Prompts\\Prompt": None,
		"scaleform\\InBrain\\HUD\\HUDElements\\QuickBar\\QuickBar": bottom_center,
		"scaleform\\InBrain\\HUD\\HUDElements\\ContextualLegends\\ContextualLegends": None,
		# "scaleform\\inbrain\\video\\video"
		# "scaleform\\others\\rootmovie\\rootmovie"
		# "scaleform\\Others\\ComponentLibrary\\Skinned_Components"
		# "scaleform\\Others\\Popup\\Popup"
		# "scaleform\\OuterShell\\KeyboardMapper\\KeyboardMapper"
	}

	origdata = r_dtp_movies.section.payload
	data = bytearray(origdata)

	for i in range(n_scaleform_movies):
		r_dtp_movie = r_dtp_movies.add(0xC0*i)
		r_name = r_dtp_movie.deref(0)
		name = r_name.access_null_terminated().decode("ascii") # if something weird shows up and 'utf-8' doesn't work, try 'latin1'
		dim = r_dtp_movie.access(f32x4, 0x30)

		print("{:3} {}".format(i, name))
		newdim = patch.get(name, None)
		if newdim is not None:
			print("     {} {} {} {} -> {} {} {} {}".format(*(dim + newdim)))
			dimbytes = struct.pack("<ffff", *newdim)
			data[
				r_dtp_movie.offset + 0x30:
				r_dtp_movie.offset + 0x40] = dimbytes

	r_dtp_movies.section.payload = bytes(data)

	modified_drm = extra.write(sections, rootsectionindex)
	fname = "scaleui_{}".format(scale).replace(".", "_") + ".000"
	with open(fname, "wb") as f:
		bigfile.write_bigfile(f, [
			(b"pc-w\\globalscaleformdatabase.drm", 0xffffffff, modified_drm)
		])

	r_dtp_movies.section.payload = origdata


build_patch(1.2)
build_patch(1.5)
build_patch(2.0)
