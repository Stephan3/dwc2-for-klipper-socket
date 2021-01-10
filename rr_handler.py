
import tornado.web
from tornado.ioloop import IOLoop
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
		self.init_done = dwc2.init_done
		self.regex_filter = '|'.join(dwc2.regex_filter)

	async def get(self, *args):

		repl_ = None
		if self.request.remote_ip not in self.clients.keys() and "rr_connect" not in self.request.uri and self.request.remote_ip != '127.0.0.1':
			#	response 408 timeout to force the webif reload after klippy restarts us
			self.clear()
			self.set_status(408)
			self.finish()
			return

		if self.request.remote_ip in self.clients.keys():
			self.clients[self.request.remote_ip]['last_seen'] = time.time()

		#	polldata fetch - curl http://127.0.0.1:4750/rr_poll_data |jq
		if "rr_poll_data" in self.request.uri:
			self.write(json.dumps(self.poll_data))
			return
		#	clients - curl http://127.0.0.1:4750/rr_clients |jq
		if "rr_clients" in self.request.uri:
			self.write(json.dumps(self.clients))
			return
		#	plopp to debug - curl http://127.0.0.1:4750/rr_entry
		if "rr_entry" in self.request.uri:
			import pdb; pdb.set_trace()
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
		if "rr_disconnect" in self.request.uri:
			await rr_disconnect(self)
			return
		if "rr_download" in self.request.uri:
			await rr_download(self)
			return
		if "rr_fileinfo" in self.request.uri:
			repl_ = await rr_fileinfo(self)
			self.write(repl_)
			return
		#	filehandling - dirlisting
		if "rr_filelist" in self.request.uri:
			await rr_filelist(self)
			return
		#	running gcodes
		if "rr_gcode" in self.request.uri:
			await rr_gcode(self)
			return
		#	creating directories
		if "rr_mkdir" in self.request.uri:
			await rr_mkdir(self)
			return
		#	moving files/dirs
		if "rr_move" in self.request.uri:
			await rr_move(self)
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
		io_loop = IOLoop.current()
		io_loop.call_later(600, clear_client, self.request.remote_ip, self)

	self.write(json.dumps({
		"err":0,
		"sessionTimeout":8000,	#	config value?
		"boardType":"duetmaestro"	#	that one is for you immutef
	}))

	#
async def rr_config(self):

	if not self.klippy.connected or not self.init_done or \
		'Printer is ready' != self.poll_data.get('webhooks', {}).get('state_message', "Knackwurst"):
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

	config = self.poll_data['configfile']['config']
	x = config.get('stepper_x', config.get('stepper_a'))
	y = config.get('stepper_y', config.get('stepper_b'))
	z = config.get('stepper_z', config.get('stepper_c'))

	self.write(json.dumps({
		#	min(with posmin?)
		"axisMins": [ 	float( x.get('position_endstop', x.get('position_min', 0)) ),
						float( y.get('position_endstop', y.get('position_min', 0)) ),
						float( z.get('position_endstop', z.get('position_min', 0)) )
		],
		"axisMaxes": [	float( x.get('position_max', 0) ),
						float( y.get('position_max', 0) ),
						float( z.get('position_max', 0) )
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
	if not self.sd_root:
		self.write({'err': 1})
		return

	path_ = self.sd_root + self.get_argument('name').replace("0:", "")

	if os.path.isdir(path_):
		shutil.rmtree(path_)

	if os.path.isfile(path_):
		os.remove(path_)

	self.write({'err': 0})
async def rr_disconnect(self):
	self.clients.pop(self.request.remote_ip, None)
async def rr_download(self):

	if self.sd_root:
		path = self.sd_root + self.get_argument('name').replace("0:", "")
	else:
		path = None

	#	ovverride for config file
	if "config.g" in self.get_argument('name').replace("0:", ""):
		path = self.poll_data['info']['config_file']

	#	handle heigthmap
	if 'heightmap.csv' in path:
		repl_ = get_heigthmap(self)
		if repl_ and path:
			with open(path, "w") as f:
				for line in repl_:
					f.write( line + '\n')

	if os.path.isfile(path):

		self.set_header( 'Content-Type', 'application/force-download' )
		self.set_header( 'Content-Disposition', 'attachment; filename=%s' % os.path.basename(path) )

		with open(path, "rb") as f:
			self.write( f.read() )
async def rr_fileinfo(self):
	if not self.sd_root:
		self.write({'err': 1})
		return

	path = None

	try:
		path = self.sd_root + self.get_argument('name').replace("0:", "")
	except:
		#	happens if we sart midprint
		selcted = self.poll_data['print_stats']['filename']
		if selcted:
			path = self.sd_root + '/' + selcted

	if path:
		return parse_gcode(path, self)
	else:
		return {}
async def rr_filelist(self):

	directory = self.get_argument('dir', self.poll_data['last_path'])

	#	creating the infoblock
	response = {
		"dir": directory ,
		"first": self.get_argument('first', 0) ,
		"files": [] ,
		"next": 0 ,
		"err": 0
	}

	#	virtual config file
	if "/sys" in directory.replace("0:", ""):
		response['files'].append({
			"type": "f",
			"name": "config.g" ,
			"size": 1 ,
			"date": datetime.datetime.fromtimestamp(os.stat(self.poll_data.get('info',{}).get('config_file',1)).st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
		})

	if not self.sd_root:
		if "/sys" in directory.replace("0:", ""):
			self.write(json.dumps(response))
		else:
			self.write(json.dumps({'err':1}))
			self.clients[self.request.remote_ip]['gcode_replys'].append("Error: Can´t detect virtual sdcard.")
		return

	path = self.sd_root + directory.replace("0:", "")

	#	if rrf is requesting directory, it has to be there.
	if not os.path.exists(path):
		pass

	#	append elements to files list matching rrf syntax
	if os.path.exists(path):

		for file in os.listdir(path):
			os.rename(os.path.join(path, file), os.path.join(path, file.replace(' ', '_')))

		for el_ in os.listdir(path):
			el_path = path + "/" + str(el_)
			response['files'].append({
				"type": "d" if os.path.isdir(el_path) else "f" ,
				"name": str(el_) ,
				"size": os.stat(el_path).st_size ,
				"date": datetime.datetime.fromtimestamp(os.stat(el_path).st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
		})

	#	add klipper macros as virtual files
	if len(self.poll_data['klipper_macros']) > 0 and self.get_argument('dir').replace("0:", "") == '/macros':
		response['files'].append({
			"type": "d" ,
			"name": "Klipper" ,
			"date": datetime.datetime.fromtimestamp(os.stat(self.poll_data.get('info',{}).get('config_file',1)).st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
		})
	if self.get_argument('dir').replace("0:", "") == '/macros/Klipper':
		for macro in self.poll_data['klipper_macros']:
			response['files'].append({
				"type": "f" ,
				"name": macro ,
				"size": 1 ,
				"date": datetime.datetime.fromtimestamp(os.stat(self.poll_data.get('info',{}).get('config_file',1)).st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
			})

	self.poll_data['last_path'] = path
	self.write(json.dumps(response))
	#
async def rr_gcode(self):

	gcodes = str( self.get_argument('gcode') ).replace('0:', '').replace('"', '').split("\n")

	#	Handle emergencys - just do it now
	for code in gcodes:
		if 'M112' in code:
			cmd_M112(self)

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
		'M141': cmd_M141 ,
		'M290': cmd_M290 ,		#	set babysteps
		'M999': cmd_M999		#	issue restart
	}
	handover = ""
	for g in gcodes:

		params = parse_params(g)
		execute = params['#original']

		if params['#command'] in rrf_commands.keys():
			func_ = rrf_commands.get(params['#command'])
			execute = func_(params, self)

		handover += execute + "\n"

	req_ = self.klippy.form_request( "gcode/script", {'script': handover} )
	self.pending_requests[req_.id] = req_
	await self.klippy.send_request(req_)

	try:
		res = await req_.wait(6)	#	needs 6 as dwc webapp is waiting 8
	except Exception as e:
		#	asume longrunning command
		print("timeout reached with: " + str(e))
		self.write(json.dumps(""))
		return

	if 'error' in res.keys():
		#		bluebear will tell us
		self.write(json.dumps('{"buff": 241}'))
	else:
		self.clients[self.request.remote_ip]['gcode_replys'].append("")
		self.write('{"buff": 241}')
	return

	#
async def rr_mkdir(self):
	path = self.sd_root + self.get_argument('dir').replace("0:", "").replace(' ', '_')
	if not os.path.exists(path):
		os.makedirs(path)
		return await rr_filelist(self)
	return {'err': 1}
async def rr_move(self):
	if "config.g" in self.get_argument('old').replace("0:", ""):
		src_ = self.poll_data.get('info',{}).get('config_file',1)
		dst_ = self.poll_data.get('info',{}).get('config_file',1) + ".backup"
		shutil.copyfile(src_ , dst_)
		return {'err': 0} #await rr_filelist(self)
	else:
		src_ = self.sd_root + self.get_argument('old').replace("0:", "")
		dst_ = self.sd_root + self.get_argument('new').replace("0:", "")
	try:
		shutil.move(src_ , dst_)
	except Exception as e:
		return {"err": 1}
	return await rr_filelist(self)
async def rr_reply(self):
	output = ""
	try:
		reps = self.clients[self.request.remote_ip]['gcode_replys']
		if len(reps) > 10:
			while len(reps) > 0:
				line = reps.pop(0)
				line = line.replace("!!", "Error: ").replace("//", "")
				replys = line.split('\n')
				for r_ in replys:
					if translate_status(self) == 'P' and re.findall(self.regex_filter, r_):
						continue
					output += re.sub(r'^\s', '', r_) + '\n'
		else:
			line = reps.pop(0)
			line = line.replace("!!", "Error: ").replace("//", "")
			replys = line.split('\n')
			for r_ in replys:
				if translate_status(self) == 'P' and re.findall(self.regex_filter, r_):
					continue
				output += re.sub(r'^\s', '', r_) + '\n'
	except Exception as e:
		pass
	else:
		self.write(output)
async def rr_status(self, status=0):

	def get_axes_homed():
		q_ = self.poll_data.get('toolhead', {}).get('homed_axes', [])
		return [ 1 if "x" in q_ else 0 , 1 if "y" in q_ else 0 , 1 if "z" in q_ else 0 ]

	#	if no klippy connection there provide minimalistic dummy data
	if not self.klippy.connected or \
		not self.init_done or translate_status(self) == 'O':
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

	gcode_move = self.poll_data.get('gcode_move', {})

	response = {
		"status": translate_status(self),
		"coords": {
			"axesHomed": get_axes_homed(), # [1,1,1]
			"xyz": [a - b for a, b in zip(gcode_move.get('position',[0,0,0,0])[:3], gcode_move.get('homing_origin',[0,0,0,0]))] ,
			"machine": [ 0, 0, 0 ],			#	what ever this is? no documentation.
			"extr": gcode_move.get('position',[0,0,0,0])[3:]
		},
		"speeds": {
			"requested": gcode_move.get('speed', 60) / 60 ,	#	only last speed not current
			"top": 	gcode_move.get('speed', 60) / 60 * gcode_move.get('speed_factor', 1) #	not available on klipepr
		},
		"currentTool": 0, #self.current_tool,	#	still not cool
		"params": {
			"atxPower": -1,
			"fanNames": [ "" ],
			"fanPercent": [ self.poll_data.get('fan', {}).get('speed', 0)*100 ] ,
			"speedFactor": gcode_move.get('speed_factor',1) * 100,
			"extrFactors": [ gcode_move.get('extrude_factor',1) * 100 ],
			"babystep": gcode_move.get('homing_origin',[0,0,0])[2]
			},
		"seq": len(self.clients[self.request.remote_ip]['gcode_replys']) ,
		"sensors": {
			"fanRPM": [ -1 ]
		},
		"time": self.poll_data.get('toolhead', {}).get('print_time', 0) ,	#	feels wrong unsure about that value
		"temps": {
			#	this can be better -> will fail onprinters without a bed -> will fail on machines with more that 1 extruder
			"bed": {
				"current": self.poll_data.get('heater_bed',{}).get('temperature', 0) ,
				"active": self.poll_data.get('heater_bed',{}).get('target', 0) ,
				"state": 0 if self.poll_data.get('heater_bed',{}).get('target',0) < 20 else 2 ,
				"heater": 0
			},
			"current": [ self.poll_data.get('heater_bed',{}).get('temperature',0), self.poll_data['extruder']['temperature'] ] ,
			"state": [ 0 if self.poll_data.get('heater_bed',{}).get('target',0) < 20 else 2, 0 if self.poll_data['extruder']['target'] < 20 else 2 ] ,
			"names": [ "Bed" ] + [ "extruder0" ] ,	#	name is 0 for a extruder 0
			"tools": {
				"active": [ [ self.poll_data['extruder']['target'] ] ],
				"standby": [ [ 0 ] ]
			},
			#	for loop that gives extrasensors available?
			"extra": []
		},
		#
		#	STATUS 2 from here
		#
		"coldExtrudeTemp": int(self.poll_data['configfile']['config'].get('extruder', {}).get('min_extrude_temp', 170)) ,
		"coldRetractTemp": int(self.poll_data['configfile']['config'].get('extruder', {}).get('min_extrude_temp', 170)) ,
		"compensation": "None",
		"controllableFans": 1,		#	not cool
		"tempLimit": int(self.poll_data['configfile']['config'].get('extruder', {}).get('max_temp', 280)) ,
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
			"threshold": 2000,
			"height": 0,
			"type": 8
		},
		}
	#	tools extruder if there
	response.update({
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
		})

	#	fetch temperarutere fans
	for key in self.poll_data.keys():
		if key.startswith('temperature_fan'):
			#	chamber is this you?
			if key.endswith('chamber'):
				state = 0
				if self.poll_data[key]['target'] > 0 : state = 2
				if self.poll_data[key]['speed'] > 0 : state = 1
				response['temps'].update({
					"chamber": {
						"current": self.poll_data[key]['temperature'] ,
						"active": self.poll_data[key]['target'] ,
						"state": state ,
						"heater": 2 ,	#	extruders + bett ?
					},
					"current": response['temps']['current'] + [ self.poll_data[key]['temperature'] ],
					"state": response['temps']['state'] + [ state ] ,
					"names": response['temps']['names'] + [ "chamber" ] ,
					})
				response['temps']['extra'].append({ 'name': 'tf_chamber speed [%]',
												'temp': self.poll_data[key]['speed']*100 })
			else:
				response['temps']['extra'].append({ 'name': key,
												'temp': self.poll_data[key]['temperature'] })
	#	accels as graph
	response['temps']['extra'].append({ 'name': 'max_accel  [*10]', 'temp': self.poll_data['toolhead']['max_accel']/10 })
	if status == 3:
		k_stats = self.poll_data.get('print_stats', {})
		sdcard = self.poll_data.get('virtual_sdcard', {})

		try:
			f_data = self.poll_data['running_file']
		except Exception as e:
			f_data = self.poll_data['running_file'] = await rr_fileinfo(self)
		duration = round( k_stats.get('print_duration', 1), 3)	#	dur in secs
		progress = round( sdcard.get('progress', 1), 3)	#	prgress fkt
		filament_used = max( k_stats.get('filament_used', 1), .1)
		filament_togo = sum(f_data.get('filament', [1])) - filament_used

		response.update({
			"currentLayer": 0,
			"currentLayerTime": 0,
			"extrRaw": [ filament_used ],
			"fractionPrinted": progress,
			"filePosition": sdcard.get('file_position', 0),
			"firstLayerDuration": 0,
			"firstLayerHeight": f_data.get('firstLayerHeight', 0),
			"printDuration": duration,
			"warmUpDuration": k_stats.get('total_duration', 0) - duration,
			"timesLeft": {
				"file": (1-progress) * duration / max( progress, 0.000001),
				"filament": filament_togo * duration / filament_used,
				"layer": 60 #self.print_data['tleft_layer']
			}
		})

	self.write(response)
async def rr_upload(self):

	ret_ = {"err":1}
	if self.sd_root:
		path = self.sd_root + self.get_argument('name').replace("0:", "").replace(' ', '_')
	else:
		path = None

	if "config.g" in self.get_argument('name'):
		path = self.poll_data['info']['config_file']

	dir_ = os.path.dirname(path)
	if not os.path.exists(dir_):
		os.makedirs(dir_)

	open(path.replace(" ","_"), "wb").write(self.request.body)

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
	response = "SDCARD_RESET_FILE" + "\n"
	path = self.sd_root + "/macros/print/cancel.g"
	if os.path.isfile(path):
		response += rrf_macro(path)
	elif 'CANCEL_PRINT' in self.poll_data['klipper_macros']:
		response += 'CANCEL_PRINT'
	return response
# 	rrf M24 - start/resume print from sdcard
def cmd_M24(params, self):
	response = 'M24\n'
	#	rrf resume macro
	if self.poll_data['virtual_sdcard']['file_position']> 0:
		path = self.sd_root + "/macros/print/resume.g"
		if os.path.isfile(path):
			response += rrf_macro(path)
		elif 'RESUME_PRINT' in self.poll_data['klipper_macros']:
			response += 'RESUME_PRINT'
	return response
#	rrf M25 - pause print
def cmd_M25(params, self):
	response = 'M25\n'
	self.poll_data['pausing'] = True
	#	rrf pause macro:
	path = self.sd_root + "/macros/print/pause.g"
	if os.path.isfile(path):
		response += rrf_macro(path)
	elif 'PAUSE_PRINT' in self.poll_data['klipper_macros']:
		response += 'PAUSE_PRINT'
	return response
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
		klipma = params['#original'].split("/")[-1]
		if klipma in self.poll_data['klipper_macros']:
			return klipma
		else:
			return 0
	else:
		return rrf_macro(path)
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
	return 'SAVE_GCODE_STATE NAME=DWC_BOTTON'
#	restore states butttons
def cmd_M121(params, self):
	return 'RESTORE_GCODE_STATE NAME=DWC_BOTTON MOVE=0'
def cmd_M141(params, self):
	target = int( params['S'] )
	return 'SET_TEMPERATURE_FAN_TARGET temperature_fan=chamber target=' + str(target)
#	setting babysteps:
def cmd_M290(params, self):
	mm_step = float( params['Z'] )
	return 'SET_GCODE_OFFSET Z_ADJUST=' + str(mm_step) + ' MOVE=1'
def cmd_M999(params, self):
	self.init_done = False
	return 'RESTART'
#
#
#

def get_heigthmap(self):
	def calc_mean(matrix_):

		matrix_tolist = []
		for line in matrix_:
			matrix_tolist += line

		return float(sum(matrix_tolist)) / len(matrix_tolist)

	def calc_stdv(matrix_):
		from statistics import stdev

		matrix_tolist = []
		for line in matrix_:
			matrix_tolist += line

		return stdev(matrix_tolist)

		#

	bed_mesh = self.poll_data.get('bed_mesh', {})

	if bed_mesh.get('probed_matrix', None):
		hmap = []
		z_matrix = bed_mesh['mesh_matrix']
		#z_matrix = bed_mesh['probed_matrix']
		mesh_data = bed_mesh				#	see def print_mesh in bed_mesh.py line 572

		meane_ = round( calc_mean(z_matrix), 3)
		stdev_ = round( calc_stdv(z_matrix) , 3)

		hmap.append( 'RepRapFirmware height map file v2 generated at ' + str(datetime.datetime.now().strftime('%Y-%m-%d %H:%M')) + ', mean error ' + str(meane_) + ', deviation ' + str(stdev_))
		hmap.append('xmin,xmax,ymin,ymax,radius,xspacing,yspacing,xnum,ynum')
		xspace_ = ( mesh_data['mesh_max'][0] - mesh_data['mesh_min'][0] ) /  len(z_matrix[0])
		yspace_ = ( mesh_data['mesh_max'][1] - mesh_data['mesh_min'][1] ) / len(z_matrix)
		hmap.append( str(mesh_data['mesh_min'][0]) + ',' + str(mesh_data['mesh_max'][0]) + ',' + str(mesh_data['mesh_min'][1]) + ',' + str(mesh_data['mesh_max'][1]) + \
			',-1.00,' + str(xspace_) + ',' + str(yspace_) + ',' + str( len(z_matrix[0])) + ',' + str(len(z_matrix)) )

		for line in z_matrix:
			read_by_offset = map(lambda x: x-meane_,line)
			read = map(lambda x: x-meane_,line)
			hmap.append( '  ' + ',  '.join( map(str, read) ))

		return hmap

	else:
		self.clients[self.request.remote_ip]['gcode_replys'].append("Bed has not been probed")
		return
def clear_client(client_ip, self):
	if time.time() - self.clients.get(self.request.remote_ip, {}).get('last_seen', 0) > 1800:
		self.clients.pop(self.request.remote_ip, None)
	else:
		self.ioloop.call_later(600, clear_client, client_ip, self)
def parse_gcode(path, self):
	slicers = {
		'Cura':
			{
				'name': 'with\s(.+?)_SteamEngine',
				'version': 'SteamEngine\s(.+?)\n',
				'object_h': ';MAXZ:\d+.\d',
				'first_h': ';MINZ:\d+.\d',
				'layer_h': ';Layer height: \d.\d+',
				'duration': ';TIME:\d+',
				'filament': [ ';Filament used: \d*.\d+m' , 1000 ]
			},
		'ideaMaker':
			{
				'name': ';Sliced by (ideaMaker?)',
				'version': ';Sliced by ideaMaker(.+?),',
				'object_h': ';Z:\d+.\d+',
				'first_h': ';Z:\d+.\d+',
				'layer_h': ';HEIGHT:\d+.\d+',
				'duration': ';Print Time:.*',
				'filament': [ ';Material.*1 Used: \d+.\d' , 1 ]
			},
		'KISSlicer':
			{
				'name': '; (KISSlicer?) - .*',
				'version': '; version (.+\.?)',
				'object_h': '; END_LAYER_OBJECT z=.*',
				'first_h': '; END_LAYER_OBJECT z=.*',
				'layer_h': '; layer_thickness_mm =.*',
				'duration': '\s\s\d*\.\d*\sminutes',
				'filament': ['Ext.*1.*mm.*\(', 1]
			},
		'PrusaSlicer':
			{
				'name': '; generated\sby\s(PrusaSlicer?)\s\d.\d+',
				'version': ';\sgenerated\sby\sPrusaSlicer\s(.+?)\son\s.*',
				'object_h': 'G1 (Z.+?) F.*',
				'first_h': '; first_layer_height = \d.\d+\%|\d.\d+',
				'layer_h': '; layer_height = \d.\d+',
				'duration': '; estimated printing time.*(\d+d\s)?(\d+h\s)?(\d+m\s)?(\d+s)',
				'filament': [ '; filament\sused\s.mm.\s=\s[0-9\.]+', 1 ]
			},
		'Simplify3D':
			{
				'name': 'G-Code generated by\s(.+?)\(R\)',
				'version': '\sVersion\s(.*?)\n',
				'object_h' : '\sZ\\d+.\\d*',
				'first_h': '; layer 1, Z = .*',
				'layer_h': ';   layerHeight,\d.\d+',
				'duration': ';\s\s\sBuild time:\s.*',
				'filament': [ ';   Filament length: \d*.\d+', 1 ]
			},
		'SuperSlicer':
			{
				'name': '; generated\sby\s(SuperSlicer?)\s\d.\d+',
				'version': '; generated by SuperSlicer (.*?)\son\s.*',
				'object_h': 'G1\sZ\d*\.\d*',
				'first_h': '; first_layer_height = \d.\d+',
				'layer_h': '; layer_height = \d.\d+',
				'duration': '; estimated printing time.*(\d+d\s)?(\d+h\s)?(\d+m\s)?(\d+s)',
				'filament': ['; filament\sused\s.mm.\s=\s[0-9\.]+', 1]
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
				dursecs += float(re.sub('[a-z]|[A-Z]', '', extr.group())) * value

		if dursecs == 0:
			dursecs += float(''.join(re.findall("\d", in_)))

		return dursecs

	#

	metadata = { "slicer": "Slicer is not implemented" }

	#	read 20k bytes from each side
	f_size = os.stat(path).st_size
	seek_amount = min( f_size , 80000 )

	with open(path, 'rb') as f:
		content = f.readlines(seek_amount)			#	gimme the first chunk
		f.seek(0, os.SEEK_END)						#	find the end
		f.seek(seek_amount*-1,os.SEEK_CUR)			#	back up some
		content = content + f.readlines()			#	read the remainder
	content = [ x.decode('utf-8') for x in content ]
	to_analyse = " ".join(content)

	try:
		for key, value in slicers.items():
			if re.search(value['name'], to_analyse):
				version = re.search(value['version'], to_analyse).group(1)
				metadata['slicer'] = re.search(value['name'], to_analyse).group(1) + " " + version
				metadata['objects_h'] = max( [ float(mat_) for mat_ in re.findall("\d+\.\d+", \
					' '.join(re.findall(value['object_h'], to_analyse )) ) ] + [-1] )
				metadata['first_h'] = min( [ float(mat_) for mat_ in re.findall("\d+\.\d+", \
					' '.join(re.findall(value['object_h'], to_analyse )) ) ] + [10000] )
				metadata['layer_h'] = min( [ float(mat_) for mat_ in re.findall("\d+\.\d+", \
					' '.join(re.findall(value['layer_h'], to_analyse )) ) ] + [10000] )
				metadata['duration'] = calc_time( re.search(value['duration'], to_analyse ).group() )
				metadata['filament'] = max( [ float(mat_) for mat_ in re.findall("\d+\.\d+", \
					' '.join(re.findall(value['filament'][0], to_analyse )) ) ] + [-1] ) * value['filament'][1]
	except Exception as e:
		print('Error on gcode processing ' + repr(e))
		#import pdb; pdb.set_trace()

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
def rrf_macro(path):
	response = ""
	if os.path.exists(path):
		with open( path ) as f:
			lines = f.readlines()
			for line in [x.strip() for x in lines]:
				response += line + "\n"
	return response
def translate_status(self):

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

	if 'Printer is ready' != self.poll_data.get('webhooks', {}).get('state_message', "Knackwurst") :
		return 'O'

	if self.poll_data['idle_timeout']['state'] == 'Printing':
		state = 'B'

	stats = self.poll_data.get('print_stats', None)
	if stats:
		s_ = stats['state']
		if s_ == 'printing': state = 'P'
		if self.poll_data.get('pausing', False): state = 'D'
		if s_ == 'paused':
			state = 'S'
			self.poll_data['pausing'] = False
	else:
		self.poll_data['pausing'] = False

	return state
