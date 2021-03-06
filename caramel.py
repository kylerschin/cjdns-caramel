#!/usr/bin/python3

import json
import os.path
import subprocess

from gi.repository import GLib
from gi.repository import Gtk
from main_window import MainWindow

from rpc_connection import *
from cjdns_config import *

class CaramelApplication(Gtk.Application):
	def __init__(self):
		Gtk.Application.__init__(self, application_id = 'info.cjdns.caramel')
		self.connect("activate", self.activate)

	def activate(self, data=None):
		self.window = MainWindow(self)
		self.add_window(self.window)
		
		self.cjdroute_path = None
		self.load_or_create_config()
		
		self.rpc_conn = None
		self.reset_connection()

		self.update_status()
		GLib.timeout_add_seconds(5, self.update_status)

	def load_or_create_config(self):
		self.config = None
		config_path = os.path.expanduser("~/.config/cjdroute.conf")

		if os.path.exists(config_path):
			self.load_config(config_path)
		elif self.cjdroute_path is not None:
			self.create_config(config_path)
		else:
			# Completely unconfigured, no idea where cjdroute is
			self.window.cjdroute_path_infobar.show()

		if self.config is None:
			self.rpc_settings = {'host': '127.0.0.1', 'port': 11234}
		else:
			self.rpc_settings = self.config.rpc_settings()

		self.window.credentials_page.update()

	def load_config(self, config_path):
		self.config = CjdnsConfig(config_path)
		self.config.load()

		# Use cjdroute.conf to guess where the cjdns directory is
		self.cjdroute_path = self.config.config.get('cjdroutePath')

	def create_config(self, config_path):
		self.config = CjdnsConfig(config_path)
		self.config.generate(self.cjdroute_path)
		self.config.config['cjdroutePath'] = self.cjdroute_path
		self.config.save()

	def generate_authorized_password(self):
		if self.cjdroute_path is None:
			return None

		temp_config = CjdnsConfig(None)
		temp_config.generate(self.cjdroute_path)

		return temp_config.config['authorizedPasswords'][0]['password']

	def start_cjdns(self):
		proc = subprocess.Popen(['pkexec', '--user', 'root', self.cjdroute_path], stdin=subprocess.PIPE,  close_fds=True)

		proc.stdin.write(self.config.dump().encode())
		proc.stdin.close()
		self.update_status()

	def stop_cjdns(self):
		if self.rpc_conn is not None:
			self.rpc_conn.exit()
			self.reset_connection()
			self.update_status()

	def reset_connection(self):
		if self.rpc_conn is not None:
			self.rpc_conn.close()

		self.rpc_conn = RpcConnection(
			self.rpc_settings.get('host'),
			self.rpc_settings.get('port'),
			self.rpc_settings.get('password')
		)

		return self.rpc_conn.connect()

	def update_status(self):
		def pluralize(count, word, plural):
			if count != 1:
				word = plural
			return "{0} {1}".format(count, word)

		if self.rpc_conn is not None and self.rpc_conn.broken:
			self.reset_connection()

		configured = self.config is not None

		main_status = "CJDNS is stopped"
		sub_status = None

		try:
			if self.rpc_conn.broken:
				raise ConnectionError()

			if not self.rpc_conn.ping():
				raise PingNotReturned()

			main_status = "CJDNS is running"
			connected = True

			if self.rpc_settings.get('password') is None:
				raise MissingCredentials()

			if not self.rpc_conn.test_auth():
				raise AuthFailed()

			authenticated = True

			unique_nodes = self.rpc_conn.count_unique_nodes()
			sub_status = "{0} found".format(pluralize(unique_nodes, "node", "nodes"))
					
		except ConnectionError:
			connected = False
			authenticated = False
			sub_status = "Could not connect to port {0}".format(self.rpc_conn.port)
		except PingNotReturned:
			connected = False
			authenticated = False
			sub_status = "Ping was not returned"
		except (AuthFailed, MissingCredentials):
			connected = True
			authenticated = False

		icon = {True: Gtk.STOCK_YES, False: Gtk.STOCK_NO}[connected]
		self.window.status_icon.set_from_stock(icon, Gtk.IconSize.MENU)
		self.window.status_label.set_markup('<b>' + (main_status or '') + '</b>')

		peers_markup = "<span size='small'>" + (sub_status or '') + "</span>"
		self.window.peers_label.set_markup(peers_markup)

		self.window.auth_fail_infobar.set_visible(connected and configured and not authenticated)

		self.window.start_button.set_visible(not connected)
		self.window.start_button.set_sensitive(configured and (self.cjdroute_path is not None))

		self.window.stop_button.set_visible(connected)
		self.window.stop_button.set_sensitive(authenticated)

		return True

	def locate_cjdroute(self):
		dialog = Gtk.FileChooserDialog("Locate cjdroute executable", self.window, Gtk.FileChooserAction.OPEN)
		dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		dialog.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

		response = dialog.run()

		if response == Gtk.ResponseType.OK:
			self.window.cjdroute_path_infobar.hide()
			self.cjdroute_path = dialog.get_filename()
			self.load_or_create_config()
			self.reset_connection()
			self.update_status()

		dialog.destroy()

if __name__ == "__main__":
	app = CaramelApplication()
	app.run(None)
