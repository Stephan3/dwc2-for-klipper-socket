#!/usr/bin/python3
import argparse
import json
import time
import socket
import tornado.web
import rr_handler
import os, sys
import configparser
from tornado import gen, iostream
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.locks import Event
from random import randint

class dwc2():

	def __init__(self, config):
		self.httpserver = None
		self.sd_root = None

		#	config - web section
		self.config = config
		self.web_root = os.path.expanduser( config.get('webserver', 'web_root', \
			fallback=os.path.dirname(os.path.abspath(__file__)) + "/web") )
		self.ip = config.get('webserver', 'listen_adress', fallback='0.0.0.0')
		self.port = config.get('webserver', 'port', fallback=4750)
		#	config regex
		regex = config.get('reply_filters', 'regex', fallback=None)
		if regex:
			self.regex_filter = [ x for x in regex.split('\n') if len(x)>0 ]
		self.klippy = klippy_uplink(self.process_klippy_response, self.connection_lost)
		self.pending_requests = {}
		self.clients = {}
		self.poll_data = {}
		self.poll_data['last_path'] = None
		self.poll_data['klipper_macros'] = []
		self.init_done = False

		self.ioloop = IOLoop.current()

		#
		#

	def start(self):

		def tornado_logger(req):
			fressehaltn = []
			fressehaltn = [ "/favicon.ico", "/rr_status?type=1", "/rr_status?type=2", "/rr_status?type=3", "/rr_config", "/rr_reply" ]
			values = [str(time.time())[-8:], req.request.remote_ip, req.request.method, req.request.uri]
			if req.request.uri not in fressehaltn:
				print("Tornado:" + " - ".join(values))	#	bind this to debug later

		application = tornado.web.Application(
			[
				(r"/css/(.*)", tornado.web.StaticFileHandler, {"path": self.web_root + "/css/"}),
				(r"/js/(.*)", tornado.web.StaticFileHandler, {"path": self.web_root + "/js/"}),
				(r"/fonts/(.*)", tornado.web.StaticFileHandler, {"path": self.web_root + "/fonts/"}),
				(r"/(rr_.*)", rr_handler.rr_handler, { "dwc2": self } ),
				(r"/.*", self.MainHandler, { "web_root": self.web_root }),
			],
			log_function=tornado_logger)
		self.httpserver = tornado.httpserver.HTTPServer( application, max_buffer_size=250*1024*1024 )
		self.httpserver.listen( self.port, self.ip )
		self.ioloop.spawn_callback( self.init_ )
	def config_def(section, key, default):
		res = self.config.get(section,key)
	def connection_lost(self):
		self.klippy.connected = False
		self.init_done = False
		self.ioloop.spawn_callback( self.init_ )
		res = config.get(section, key)
	async def init_(self):

		if not self.klippy.connected:
			await self.klippy.connect()
			self.ioloop.call_later(1, self.init_)
			return

		self.poll_data = {}
		self.poll_data['last_path'] = None
		self.poll_data['klipper_macros'] = []

		l_ = { "gcode/help": {}, "info": {}, "objects/list": {}, "list_endpoints": {}, "gcode/subscribe_output": { "response_template": {"DWC_2": "dwc2_subscription_to_gcode_replys"} } }
		for item in l_.keys():
			req_ = self.klippy.form_request( item, params=l_[item] )
			self.pending_requests[req_.id] = req_
			await self.klippy.send_request(req_)
			res = await req_.wait(10)
			self.poll_data[item] = res.get('result', "")
		#		subscribe to all Objects
		objects = {}
		for s_ in self.poll_data["objects/list"]['objects']:
			objects[s_] = None
		req_ = self.klippy.form_request( "objects/subscribe", params={"objects": objects, "response_template": {"its_me": "waiting_for_answers_from_klippy"} } )
		self.pending_requests[req_.id] = req_
		await self.klippy.send_request(req_)
		objects_init = await req_.wait(10)
		for key in objects_init['result']['status']:
			self.poll_data[key] = objects_init['result']['status'][key]
		#	pick sd_root from config.
		configfile = self.poll_data.get('configfile', None)
		if configfile:
			self.sd_root = os.path.expanduser( configfile.get('config',{}).get('virtual_sdcard',{}).get('path', None) )
		#	fetching klipper macros
		for key, val in self.poll_data['gcode/help'].items():
			if val == "G-Code macro":
				self.poll_data['klipper_macros'].append(key)
		self.init_done = True
	def process_klippy_response(self, out_):
		#print("GOT: \t" + json.dumps(out_))
		#	poll of incomming things, once they change
		if '\'params\'' in str(out_) and '\'status\'' in str(out_):
			for key in out_['params']['status']:
				self.poll_data[key].update(out_['params']['status'][key])
			return
		#	ids  - requests we made
		req_ = self.pending_requests.pop(out_.get('id', None), None)
		if req_:
			req_.notify(out_)
			return
		#	gcode replys that have a reply
		if 'dwc2_subscription_to_gcode_replys' in str(out_):
			for client in self.clients.keys():
				self.clients[client]['gcode_replys'].append(out_['params']['response'])
			return

		print("!! not covered !!" + json.dumps(out_))
	class MainHandler(tornado.web.RequestHandler):

		def initialize(self, web_root):
			self.web_root = web_root

		async def get(self):

			if os.path.isfile(self.web_root + self.request.uri):
				with open(self.web_root + self.request.uri, "rb") as f:
					self.write( f.read() )
					self.finish()
					return

			self.render( self.web_root + "/index.html" )
class klippy_uplink(object):

	#	example dialog:

	def __init__(self, reply_handler, connection_lost):
		self.ioloop = IOLoop.current()
		self.iostream = None
		self.reply_handler = reply_handler
		self.con_loss = connection_lost
		self.connected = False

	#	establish connection to klippys unixsocket
	async def connect(self):

		self.client = iostream.IOStream( socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) )
		try:
			await self.client.connect("/tmp/klippy_uds")
		except Exception as e:
			print("Cant connect to klippy with: " + str(e))
			self.connected = False
		else:
			self.ioloop.spawn_callback(self.read_stream, self.client)
			self.client.set_close_callback(self.con_loss)
			self.connected = True

	async def send_request(self, request):
		data = json.dumps(request.to_dict()).encode() + b"\x03"
		try:
			await self.client.write(data)
		except Exception as e:
			raise

	async def read_stream(self, stream):
		while not stream.closed():
			try:
				data = await stream.read_until(b'\x03')
			except Exception as e:
				self.con_loss
			try:
				out_ = json.loads(data[:-1])
				self.reply_handler(out_)
			except Exception as e:
				raise
				import pdb; pdb.set_trace()

	class form_request:
		def __init__(self, method, params):
			self.id = randint(100000000000, 999999999999)
			self.method = method
			self.params = params
			self._event = Event()
			self.response = None

		async def wait(self, timeout):
			start_time = time.time()
			while True:
				timeout = time.time() + timeout
				try:
					await self._event.wait(timeout=timeout)
				except TimeoutError:
					raise
				break
			#if isinstance(self.response):
			#	raise self.response
			return self.response

		def notify(self, response):
			self.response = response
			self._event.set()

		def to_dict(self):
			return {'id': self.id, 'method': self.method,
					'params': self.params}

def main():
	# set default files
	default_config = os.path.dirname(os.path.abspath(__file__)) + '/dwc2.cfg'
	default_log = "/tmp/dwc2.log"

	# parse start arguments
	parser = argparse.ArgumentParser(description="dwc2-for-klipper-socket")
	parser.add_argument("-l", "--logfile", default=default_log, metavar="<logfile>", help="log file name and location")
	parser.add_argument("-c", "--configfile", default=default_config, metavar="<logfile>", help="config file name and location")
	system_args = parser.parse_args()

	class Logger:
		def write(self, msg):
			open(system_args.logfile, "a").write(msg)
		def flush(self):
			pass

	open(system_args.logfile, "w").write("========== Started ==========\n")
	sys.stdout = Logger()
	sys.stderr = Logger()

	config = configparser.ConfigParser()
	config.read(system_args.configfile)

	io_loop = IOLoop.current()
	server = dwc2(config)

	server.start()
	io_loop.start()

	sys.stderr.close()


if __name__ == '__main__':
	main()