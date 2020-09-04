#

import tornado.web
import json
import time
import os, shutil
import datetime
import re

class rr_handler(tornado.web.RequestHandler):

	def initialize(self, dwc2):
		self.clients = dwc2.clients
		self.sd_root = dwc2.sd_root
		self.poll_data = dwc2.poll_data
		self.klippy = dwc2.klippy
		self.ioloop = dwc2.ioloop
		self.pending_requests = dwc2.pending_requests
		configfile = self.poll_data.get('configfile', None)
		if configfile:
			self.sd_root = configfile['config']['virtual_sdcard']['path']#[:-1]

	async def get(self, *args):

		repl_ = None

		#	polldata fetch - curl http://127.0.0.1:4700/rr_poll_data |jq
		if "rr_poll_data" in self.request.uri:
			self.write(json.dumps(self.poll_data))
			return
		#	clients - curl http://127.0.0.1:4700/rr_clients |jq
		if "rr_clients" in self.request.uri:
			self.write(json.dumps(self.clients))
			return
		#
		#
		#	connection request
		if "rr_connect" in self.request.uri:
			await rr_connect(self)
			return
		#	configuration
		if "rr_config" in self.request.uri:
			await rr_config(self)
			return
		if "rr_delete" in self.request.uri:
			await rr_delete(self)
			return
		if "rr_download" in self.request.uri:
			await rr_download(self)
			return
		if "rr_fileinfo" in self.request.uri:
			await rr_fileinfo(self)
			return
		#	filehandling - dirlisting
		if "rr_filelist" in self.request.uri:
			await rr_filelist(self)
			return
		#	running gcodes
		if "rr_gcode" in self.request.uri:
			await rr_gcode(self)
			return
		#	sending reply to gcodes
		if "rr_reply" in self.request.uri:
			await rr_reply(self)
			return
		#	Status request. main datatransport
		if "rr_status" in self.request.uri:
			self.clients[self.request.remote_ip]['last_seen'] = time.time()
			type_ = int( self.get_argument('type') )
			await rr_status(self, status=type_ )
			return
		#	Status request. main datatransport
		if "rr_status" in self.request.uri:
			await rr_status(self, status=type_ )
		#
		print("DWC2 - unhandled? GET " + self.request.uri)
		self.write( json.dumps({"err": "Requesttype not impelemented in dwc translator  :\n  " + self.request.uri}) )

	async def post(self, *args):

		#	filehandling - uploads
		if "rr_upload" in self.request.uri:
			await rr_upload(self)
			return
		#
		print("DWC2 - unhandled? POST " + self.request.uri)
		self.write( json.dumps({"err":1}) )
#
#
#

async def rr_connect(self):
	if self.request.remote_ip not in self.clients.keys():
		self.clients[self.request.remote_ip] = {
			"last_seen": time.time() ,
			"gcode_replys": [] ,
			"gcode_command": {}
		}

	self.write(json.dumps({
		"err":0,
		"sessionTimeout":8000,	#	config value?
		"boardType":"duetmaestro"	#	that one is for you immutef
	}))

	#
async def rr_config(self):

	if not self.klippy.connected:
		self.write(json.dumps({
			"axisMins": [],
			"axisMaxes": [],
			"accelerations": [],
			"currents": [] ,	#	can we fetch data from tmc drivers here ?
			"firmwareElectronics": "OFFLINE",
			"firmwareName": "Klipper",
			"firmwareVersion": "OFFLINE",
			"dwsVersion": "OFFLINE",
			"firmwareDate": "1970-01-01",	#	didnt get that from klippy
			"idleCurrentFactor": 30,
			"idleTimeout": 30,
			"minFeedrates": [ ] ,
			"maxFeedrates": [ ]
		}))
		return

	self.write(json.dumps({
		#	min(with posmin?)
		"axisMins": [ 	float( self.poll_data['configfile']['config']['stepper_x']['position_endstop'] ),
						float( self.poll_data['configfile']['config']['stepper_y']['position_endstop'] ),
						float( self.poll_data['configfile']['config']['stepper_z']['position_endstop'] )
		],
		"axisMaxes": [	float( self.poll_data['configfile']['config']['stepper_x']['position_max'] ),
						float( self.poll_data['configfile']['config']['stepper_y']['position_max'] ),
						float( self.poll_data['configfile']['config']['stepper_z']['position_max'] )
		],
		"accelerations": [ self.poll_data['toolhead']['max_accel'] for x in self.poll_data['toolhead']['position'] ],
		"currents": [ 0, 0, 0, 0 ] ,	#	can we fetch data from tmc drivers here ?
		"firmwareElectronics": self.poll_data['info']['cpu_info'],
		"firmwareName": "Klipper",
		"firmwareVersion": self.poll_data['info']['software_version'],
		"dwsVersion": self.poll_data['info']['software_version'],
		"firmwareDate": "1970-01-01",	#	didnt get that from klippy
		"idleCurrentFactor": 30,
		"idleTimeout": 30,
		"minFeedrates": [ 1 for x in self.poll_data['toolhead']['position'] ] ,
		"maxFeedrates": [ self.poll_data['toolhead']['max_velocity'] for x in self.poll_data['toolhead']['position'] ]	#	unitconversion ?
	}))
	#
async def rr_delete(self):
	#	lazymode_
	path_ = self.sd_root + self.get_argument('name').replace("0:", "")

	if os.path.isdir(path_):
		shutil.rmtree(path_)

	if os.path.isfile(path_):
		os.remove(path_)

	self.write({'err': 0})
async def rr_download(self):

	path = self.sd_root + self.get_argument('name').replace("0:", "")

	#	ovverride for config file
	#if "/sys/" in path and "config.g" in self.get_argument('name').replace("0:", ""):
	#	path = self.klipper_config

		#	handle heigthmap
	#	if 'heightmap.csv' in path:
	#		repl_ = self.get_heigthmap()
	##		if repl_:
	#			with open(path, "w") as f:
	#				for line in repl_:
	#					f.write( line + '\n')

	if os.path.isfile(path):

		self.set_header( 'Content-Type', 'application/force-download' )
		self.set_header( 'Content-Disposition', 'attachment; filename=%s' % os.path.basename(path) )

		with open(path, "rb") as f:
			self.write( f.read() )
async def rr_fileinfo(self):

	path = None

	try:
		path = self.sd_root + self.get_argument('name').replace("0:", "")
	except:
		selcted = self.poll_data['print_stats']['filename']
		if selcted:
			path = self.sd_root + '/' + selcted
	self.write(parse_gcode(path, self))
async def rr_filelist(self):

	path = self.sd_root + self.get_argument('dir').replace("0:", "")

	#	creating the infoblock
	repl_ = {
		"dir": self.get_argument('dir') ,
		"first": self.get_argument('first', 0) ,
		"files": [] ,
		"next": 0
	}

	#	if rrf is requesting directory, it has to be there.
	if not os.path.exists(path):
		os.makedirs(path)

	#	whitespace uploads via nfs/samba
	for file in os.listdir(path):
		os.rename(os.path.join(path, file), os.path.join(path, file.replace(' ', '_')))

	#	append elements to files list matching rrf syntax
	for el_ in os.listdir(path):
		el_path = path + "/" + str(el_)
		repl_['files'].append({
			"type": "d" if os.path.isdir(el_path) else "f" ,
			"name": str(el_) ,
			"size": os.stat(el_path).st_size ,
			"date": datetime.datetime.fromtimestamp(os.stat(el_path).st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
		})

		#	add klipper macros as virtual files
		#if "/macros" in self.get_argument('dir').replace("0:", ""):
		#	for macro_ in self.klipper_macros:

		#		repl_['files'].append({
		#			"type": "f" ,
		#			"name": macro_ ,
		#			"size": 1 ,
		#			"date": datetime.datetime.fromtimestamp(os.stat(self.klipper_config).st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
		#		})

		#	virtual config file
		#elif "/sys" in self.get_argument('dir').replace("0:", ""):

		#	repl_['files'].append({
		#		"type": "f",
		#		"name": "config.g" ,
		#		"size": os.stat(self.klipper_config).st_size ,
		#		"date": datetime.datetime.fromtimestamp(os.stat(self.klipper_config).st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
		#	})
	self.write(json.dumps(repl_))
	#
async def rr_gcode(self):

	gcodes = str( self.get_argument('gcode') ).replace('0:', '').replace('"', '').split("\n")

	#	Handle emergencys - just do it now
	for code in gcodes:
		if 'M112' in code:
			cmd_M112()

	rrf_commands = {
		'G10': cmd_G10 ,		#	set heaters temp
		'M0': cmd_M0 ,			#	cancel SD print
		'M24': cmd_M24 ,		#	resume sdprint
		'M25': cmd_M25 ,		#	pause print
		'M32': cmd_M32 ,		#	Start sdprint
		'M98': cmd_M98 ,		#	run macro
		'M106': cmd_M106 ,		#	set fan
		'M120': cmd_M120 ,		#	save gcode state
		'M121': cmd_M121 ,		#	restore gcode state
		#'M140': cmd_M140 ,		#	set bedtemp(limit to 0 mintemp)
		'M290': cmd_M290 ,		#	set babysteps
		#'M999': cmd_M999		#	issue restart
	}

	for g in gcodes:

		params = parse_params(g)
		execute = params['#original']

		if params['#command'] in rrf_commands.keys():
			func_ = rrf_commands.get(params['#command'])
			execute = func_(params, self)

		#	send request and wait for response
		req_ = self.klippy.form_request( "gcode/script", {'script': execute} )
		self.pending_requests[req_.id] = req_
		await self.klippy.send_request(req_)

		try:
			res = await req_.wait(10)
		except Exception as e:
			#	asume longrunning command
			print("timeout reached with: " + str(e))
			self.write(json.dumps(""))
			return

		if 'error' in res.keys():
			#		bluebear will tell us
			self.write(json.dumps(""))
		else:
			self.clients[self.request.remote_ip]['gcode_replys'].append("")
			self.write(json.dumps({'buff': 1}))
	return

	#
async def rr_reply(self):
	try:
		item = self.clients[self.request.remote_ip]['gcode_replys'].pop(0).replace("!!", "Error: ").replace("//", "Warning: ")
	except:
		pass
	else:
		self.write(item)
async def rr_status(self, status=0):

	def translate_status():

		#	case 'F': return 'updating';
		#	case 'O': return 'off';
		#	case 'H': return 'halted';
		#	case 'D': return 'pausing';
		#	case 'S': return 'paused';
		#	case 'R': return 'resuming';
		#	case 'P': return 'processing';	?printing?
		#	case 'M': return 'simulating';
		#	case 'B': return 'busy';
		#	case 'T': return 'changingTool';
		#	case 'I': return 'idle';

		state = 'I'
		stats = self.poll_data.get('print_stats', None)

		if 'Printer is ready' != self.poll_data.get('webhooks', {}).get('state_message', "Knackwurst") :
			return 'O'

		if self.poll_data['idle_timeout']['state'] == 'Printing':
			state = 'B'
		if stats:
			s_ = stats['state']
			if s_ == 'printing': state = 'P'
			if self.poll_data.get('pausing', False): state = 'D'
			if s_ == 'paused':
				state = 'S'
				self.poll_data['pausing'] = False		

			#	need printing here later if virtual sdcard is doing things

		return state

	def get_axes_homed():
		q_ = self.poll_data['toolhead']['homed_axes']
		return [ 1 if "x" in q_ else 0 , 1 if "y" in q_ else 0 , 1 if "z" in q_ else 0 ]

	#
	#	if no klippy connection there provide minimalistic dummy data
	if not self.klippy.connected:
		self.write(json.dumps({
			"status": "O",
			"seq": len(self.clients[self.request.remote_ip]['gcode_replys']) ,
			"coords": {
				"xyz": [] ,
				"machine": [] ,
				"extr": []
			},
			"speeds": {},
			"sensors": {
			"fanRPM": 0
			},
			"params": {
				"fanPercent": []
			} ,
			"temps": {
				"state": [],
				"extra": [{}],
				"current": [],
				"tools": { "active": [] },
				"names": []
			} ,
			"probe": {} ,
			"axisNames": "" ,
			"tools": [] ,
			"volumes": 1,
			"mountedVolumes": 1 ,
			"name": self.poll_data.get('info',{}).get('hostname', "offline")
		}))
		return

		#

	response = {
		"status": translate_status(),
		"coords": {
			"axesHomed": get_axes_homed(), # [1,1,1]
			"xyz": self.poll_data['gcode_move']['position'][:3] ,	#"xyz": [144.486,26.799,18.6]
			"machine": [ 0, 0, 0 ],			#	what ever this is? no documentation.
			"extr": self.poll_data['gcode_move']['position'][3:]
		},
		"speeds": {
			"requested": self.poll_data['gcode_move']['speed'] / 60 ,	#	speed factor?
			"top": 	0 #	not available on klipepr
		},
		"currentTool": 0, #self.current_tool,	#	still not cool
		"params": {
			"atxPower": 0,
			"fanNames": [ "" ],
			"fanPercent": [ 30 ] ,
			"speedFactor": self.poll_data['gcode_move']['speed_factor'] * 100,
			"extrFactors": [ self.poll_data['gcode_move']['extrude_factor'] * 100 ],
			"babystep": self.poll_data['gcode_move']['homing_origin'][2] # homing_origin[2]
			},
		"seq": len(self.clients[self.request.remote_ip]['gcode_replys']) ,
		"sensors": {
			"probeValue": 0,
			"fanRPM": 0
		},
		"temps": {
			"bed": {
				"current": self.poll_data['heater_bed']['temperature'] ,
				"active": self.poll_data['heater_bed']['target'] ,
				"state": 0 if self.poll_data['heater_bed']['target'] < 20 else 2 ,
				"heater": 0
			},
			#	this can be better -> will fail onprinters without a bed -> will fail on machines with more that 1 extruder
			"current": [ self.poll_data['heater_bed']['temperature'], self.poll_data['extruder']['temperature'] ] ,
			"state": [ 0 if self.poll_data['heater_bed']['target'] < 20 else 2, 0 if self.poll_data['extruder']['target'] < 20 else 2 ] ,
			"names": [ "Bed" ] + [ "extruder0" ] ,	#	name is 0 for a extruder 0
			"tools": {
				"active": [ [ self.poll_data['extruder']['target'] ] ],
				"standby": [ [ 0 ] ]
			},
			#	for loop that gives extrasensors available?
			"extra": [
				{
					"name": "*MCU",
					"temp": 0
				}
			]
		},
		"time": self.poll_data['toolhead']['print_time'] ,	#	feels wrong unsure about that value
		#
		#	STATUS 2 from here
		#
		"coldExtrudeTemp": int(self.poll_data['configfile']['config']['extruder']['min_extrude_temp']) ,
		"coldRetractTemp": int(self.poll_data['configfile']['config']['extruder']['min_extrude_temp']) ,
		"compensation": "None",
		"controllableFans": 1,		#	not cool
		"tempLimit": int(self.poll_data['configfile']['config']['extruder']['max_temp']) ,
		"endstops": 4088,	#	what does this do?
		"firmwareName": "Klipper",
		"geometry": self.poll_data['configfile']['config']['printer']['kinematics'],
		"axes": len(get_axes_homed()),
		"totalAxes": len(get_axes_homed()) + 1,
		"axisNames": "XYZ", #+ "".join([ "U" for ex_ in extr_stat ]),
		"volumes": 1,
		"mountedVolumes": 1,
		"name": self.poll_data['info']['hostname'],
		"probe": {
			"threshold": 100,
			"height": 0,
			"type": 8
		},
		"tools": [
			{
				"number": 0,
				"name": "extruder0",
				"heaters": [ 1 ] ,
				"drives": [ 0 ] ,
				"axisMap": [ 1 ],
				"fans": 1,
				"filament": "",
				"offsets": [ 0, 0, 0 ]
			} ]
	}

	if status == 3:
		stats = self.poll_data.get('print_stats', {})
		sdcard = self.poll_data.get('virtual_sdcard', {})

		duration = round( stats.get('print_duration', 1), 3)	#	dur in secs
		progress = round( sdcard.get('progress', 1), 3)	#	prgress fkt

		response.update({
			"currentLayer": 0,
			"currentLayerTime": 0,
			"extrRaw": [ stats.get('filament_used', 0) ],
			"fractionPrinted": progress,
			"filePosition": sdcard.get('file_position', 0),
			"firstLayerDuration": 0,
			"firstLayerHeight": 0,
			"printDuration": duration,
			"warmUpDuration": stats.get('total_duration', 0) - duration,
			"timesLeft": {
				"file": (1-progress) * duration\
					/ max( progress, 0.000001), #self.print_data['tleft_file'],
				"filament": 60, #self.print_data['tleft_filament'],
				"layer": 60 #self.print_data['tleft_layer']
			}
		})
	self.write(response)
async def rr_upload(self):

	path = self.sd_root + self.get_argument('name').replace("0:", "").replace(' ', '_')
	dir_ = os.path.dirname(path)

	ret_ = {"err":1}

	if not os.path.exists(dir_):
		os.makedirs(dir_)

	#	klipper config ecxeption
	#if "/sys/" in path and "config.g" in self.get_argument('name'):
	#	path = self.klipper_config

	with open(path.replace(" ","_"), 'w') as out:
		out.write(self.request.body.decode('utf-8'))

	if os.path.isfile(path):
		ret_ = {"err":0}

	self.write(json.dumps(ret_))
#
#
#

#	rrf G10 command - set heaterstemp
def cmd_G10(params, self):
	return str("M104 T%d S%0.2f" % ( int(params['P']), int(params['S']) ) )
#	rrf M0 - cancel print from sd
def cmd_M0(params, self):
	return "SDCARD_RESET_FILE"
# 	rrf M24 - start/resume print from sdcard
def cmd_M24(params, self):
		if self.poll_data['virtual_sdcard']['file_position']> 0:
			pass
			#	resume macro
		else:
			self.print_data = {
				"print_start": time.time() ,
				"print_dur": 0 ,
				"extr_start": sum(self.poll_data['gcode_move']['position'][3:]) ,
				"firstlayer_dur": 0 ,
				"curr_layer": 1 ,
				"curr_layer_start": 0 ,
				"curr_layer_dur" : 0 ,
				"heat_time": 0 ,
				"last_zposes": [ self.poll_data['gcode_move']['position'][3] for n_ in range(10) ] ,
				"last_switch_z": 0,
				"tleft_file": 99999999999,
				"tleft_filament": 99999999999,
				"tleft_layer": 99999999999,
				"layercount": 0, #self.file_infos.get('running_file', {}).get('layercount', 1),
				"filament": 0, #self.file_infos.get('running_file', {}).get( "filament", 1)
			}
			#self.reactor.register_callback(self.update_printdata, waketime=self.reactor.monotonic() + 2)
		return 'M24\n'
#	rrf M25 - pause print
def cmd_M25(params, self):
	self.poll_data['pausing'] = True
	return 'M25'
#	rrf M32 - start print from sdcard
def cmd_M32(params, self):

	#	file dwc1 - 'zzz/simplify3D41.gcode'
	#	file dwc2 - '/gcodes/zzz/simplify3D41.gcode'
	file = '/'.join(params['#original'].split(' ')[1:])
	if '/gcodes/' not in file:	#	DWC 1 work arround
		fullpath = '/gcodes/' + params['#original'].split()[1]
	else:
		fullpath = file

	return 'SDCARD_PRINT_FILE FILENAME=' + fullpath + '\n'
#	start macro
def cmd_M98(params, self):

	path = self.sd_root + "/" + "/".join(params['#original'].split("/")[1:])

	if not os.path.exists(path):
		return
		#	now we know its no macro file
		klipma = params['#original'].split("/")[-1].replace("\"", "")
		if klipma in self.klipper_macros:
			return klipma
		else:
			return 0
	else:
		#	now we know its a macro from dwc
		response = ""
		with open( path ) as f:
			lines = f.readlines()
			for line in [x.strip() for x in lines]:
				response += line + "\n"
			return response
#	rrf M106 translation to klipper scale
def cmd_M106(params, self):

	if float(params['S']) < 1.01:
		command = str( params['#command'] + " S" + str(int( float(params['S']) * 255 )) )
	else:
		command = str( params['#command'] + " S" + str(int( float(params['S']) )) )

	if float(params['S']) < .05:
		command = str("M107")

	return command
#	emergency
def cmd_M112(self):
	req_ = self.klippy.form_request( "emergency_stop", {} )
	self.ioloop.spawn_callback(self.klippy.send_request, req_)
#	save states butttons
def cmd_M120(params, self):
	return "SAVE_GCODE_STATE NAME=DWC_BOTTON"
#	restore states butttons
def cmd_M121(params, self):
	return "RESTORE_GCODE_STATE NAME=DWC_BOTTON MOVE=0"

#	setting babysteps:
def cmd_M290(params, self):

	mm_step = float( params['Z'] )
	command = 'SET_GCODE_OFFSET Z_ADJUST=' + str(mm_step) + ' MOVE=1'

	return command

#
#
#

def parse_gcode(path, self):
	slicers = {
		'Cura':
			{
				'name': 'Cura_SteamEngine.*',								#	somewhere in the first lines
				'object_h': '\sZ\\d+.\\d*',									#	get the highest knowing z
				'first_h': '\sZ\\d+.\\d\s',									#	get the lowest knowing z
				'layer_h': ';Layer height: \d.\d+',							#	its there
				'duration': ';TIME:\\d+',									#	its there
				'filament': ';Filament used: \d*.\d+m'						#	its there
			},
		'SuperSlicer':
			{
				'name': 'SuperSlicer',										#	somewhere in the first lines
				'object_h': 'G1\sZ\d*\.\d*',								#	get the highest knowing z
				'first_h': '; first_layer_height = \d.\d+',					#	its there
				'layer_h': '; layer_height = \d.\d+',						#	its there
				'duration': '; estimated printing time.*(\d+d\s)?(\d+h\s)?(\d+m\s)(\d+s)',			#	its there 		update: 03-09-2020
				'filament': '; filament\sused\s.mm.\s=\s[0-9\.]+'			#	its there
			}
	}

	def calc_time(in_):

		dimensions = {
			'(\d+(\s)?days|\d+(\s)?d)': 86400 ,
			'(\d+(\s)?hours|\d+(\s)?h)': 3600 ,
			'(([0-9]*\.[0-9]+)\sminutes|\d+(\s)?m)': 60 ,
			'(\d+(\s)?seconds|\d+(\s)?s)': 1
		}
		dursecs = 0
		for key, value in dimensions.items():
			extr = re.search(re.compile(key),in_)
			if extr:
				dursecs += int(re.sub('[a-z]|[A-Z]', '', extr.group())) * value

		return dursecs

	#

	metadata = { "slicer": "Slicer is not implemented" }

	#	read 20k bytes from each side
	f_size = os.stat(path).st_size
	seek_amount = min( f_size , 20000 )

	with open(path, 'rb') as f:
		content = f.readlines(seek_amount)			#	gimme the first chunk
		f.seek(0, os.SEEK_END)						#	find the end
		f.seek(seek_amount*-1,os.SEEK_CUR)			#	back up some
		content = content + f.readlines()			#	read the remainder
	content = [ x.decode('utf-8') for x in content ]
	to_analyse = " ".join(content)

	for key, value in slicers.items():
		if re.compile(value['name']).search(to_analyse):
			metadata['slicer'] = re.search(re.compile(value['name']),to_analyse).group()
			metadata['objects_h'] = max( [ float(mat_) for mat_ in re.findall("\d*\.\d*", \
				' '.join(re.findall(value['object_h'], to_analyse )) ) ] )
			metadata['first_h'] = min( [ float(mat_) for mat_ in re.findall("\d*\.\d*", \
				' '.join(re.findall(value['object_h'], to_analyse )) ) ] )
			metadata['layer_h'] = min( [ float(mat_) for mat_ in re.findall("\d*\.\d*", \
				' '.join(re.findall(value['layer_h'], to_analyse )) ) ] )
			metadata['duration'] = calc_time( re.search(value['duration'], to_analyse ).group() )
			metadata['filament'] = max( [ float(mat_) for mat_ in re.findall("\d*\.\d*", \
				' '.join(re.findall(value['filament'], to_analyse )) ) ] )

	response = {
		"size": int(os.stat(path).st_size) ,
		"lastModified": str(datetime.datetime.utcfromtimestamp( os.stat(path).st_mtime )\
			.strftime("%Y-%m-%dT%H:%M:%S")) ,
		"height": float( metadata.get("objects_h",-1 ) ) ,
		"firstLayerHeight": metadata.get("first_h",-1 ) ,
		"layerHeight": float( metadata.get("layer_h",-1) ) ,
		"printTime": int( metadata.get("duration",-1) ) ,			# in seconds
		"filament": [ float( metadata.get("filament",-1) ) ] ,		# in mm
		"generatedBy": str( metadata.get("slicer","<< Slicer not implemented >>") ) ,
		"fileName": '0:' + str(path).replace(self.sd_root, '') ,
		"layercount": ( float(metadata.get("objects_h",-1)) \
			- metadata.get("first_h",-1) ) / float(metadata.get("layer_h",-1) ) + 1 ,
		"err": 0
	}
	#import pdb; pdb.set_trace()
	return response
def parse_params(line):
	args_r = re.compile('([A-Z_]+|[A-Z*/])')
	# Ignore comments and leading/trailing spaces
	line = origline = line.strip()
	cpos = line.find(';')
	if cpos >= 0:
		line = line[:cpos]
	# Break line into parts and determine command
	parts = args_r.split(line.upper())
	numparts = len(parts)
	cmd = ""
	if numparts >= 3 and parts[1] != 'N':
		cmd = parts[1] + parts[2].strip()
	elif numparts >= 5 and parts[1] == 'N':
		# Skip line number at start of command
		cmd = parts[3] + parts[4].strip()
	# Build gcode "params" dictionary
	params = { parts[i]: parts[i+1].strip() for i in range(1, numparts, 2) }
	params['#original'] = origline
	params['#command'] = parts[1] + parts[2].strip()

	return params