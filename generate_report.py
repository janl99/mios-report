#!/usr/bin/python
__author__    = "Fabian van der Hoeven"
__copyright__ = "Copyright (C) 2013 Vermont 24x7"
__version__   = "1.0"

import optparse
import sys, os
import time
import traceback
from getpass import getpass
# Add mios-report LIB to path
try:
        mreport_home = os.environ['MREPORT_HOME']
except:
        mreport_home = "/opt/mios/mios-report"
sys.path.append(mreport_home + '/lib')

from zabbix_api import ZabbixAPI, ZabbixAPIException

import curses, os #curses is the interface for capturing key presses on the menu, os launches the files

def get_options():
	""" command-line options """

	usage = "usage: %prog [options]"
	OptionParser = optparse.OptionParser
	parser = OptionParser(usage)

	parser.add_option("-s", "--server", action="store", type="string", dest="server", help="Zabbix Server URL (REQUIRED)")
	parser.add_option("-u", "--username", action="store", type="string", dest="username", help="Username (Will prompt if not given)")
	parser.add_option("-p", "--password", action="store", type="string", dest="password", help="Password (Will prompt if not given)")

	options, args = parser.parse_args()

	if not options.server:
		show_help(parser)

	if not options.username:
		options.username = raw_input('Username: ')

	if not options.password:
		options.password = getpass()

	# apply clue to user...
	if not options.username and not options.password:
		show_help(parser)

	return options, args

def show_help(p):
	p.print_help()
	print "NOTE: Zabbix 1.8.0 doesn't check LDAP when authenticating."
	sys.exit(-1)

def errmsg(msg):
	sys.stderr.write(msg + "\n")
	sys.exit(-1)

def selectHostgroup():
	teller = 0
	hostgroups = {}
	for hostgroup in zapi.hostgroup.get({ "output": "extend", "filter": { "internal": "0"} }):
		teller+=1
		hostgroups[teller] = (hostgroup['name'], hostgroup['groupid'])
	hostgroupid = -1
	while hostgroupid == -1:
		os.system('clear')
		print "Hostgroups:"
		for hostgroup in hostgroups:
			print '\t%2d: %s' % (hostgroup, hostgroups[hostgroup][0])
		try:
			hostgroupnr = int(raw_input('Select hostgroup: '))
			try:
				hostgroupid = hostgroups[hostgroupnr][1]
				hostgroupname = hostgroups[hostgroupnr][0]
			except KeyError:
				print "\nCounting is not your geatest asset!"
				hostgroupid = -1
				print "\nPress a key to try again..."
				os.system('read -N 1 -s')
		except ValueError:
			print "\nEeuhm... I don't think that's a number!"
			hostgroupid = -1
			print "\nPress a key to try again..."
			os.system('read -N 1 -s')
		except KeyboardInterrupt: # Catch CTRL-C
			pass
	return (hostgroupid, hostgroupname)

def getGraph(graphid):
	import pycurl
	import StringIO
	curl = pycurl.Curl()
	buffer = StringIO.StringIO()

	z_server = options.server
	z_user = options.username
	z_password = options.password
	z_url_index = z_server + 'index.php'
	z_url_graph = z_server + 'chart2.php'
	z_login_data = 'name=' + z_user + '&password=' + z_password + '&autologon=1&enter=Sign+in'
	# When we leave the filename of the cookie empty, curl stores the cookie in memory
	# so now the cookie doesn't have to be removed after usage. When the script finishes, the cookie is also gone
	z_filename_cookie = ''
	z_image_name = str(graphid) + '.png'
	# Log on to Zabbix and get session cookie
	curl.setopt(curl.URL, z_url_index)
	curl.setopt(curl.POSTFIELDS, z_login_data)
	curl.setopt(curl.COOKIEJAR, z_filename_cookie)
	curl.setopt(curl.COOKIEFILE, z_filename_cookie)
	curl.perform()
	# Retrieve graphs using cookie
	# By just giving a period the graph will be generated from today and "period" seconds ago. So a period of 604800 will be 1 week (in seconds)
	# You can also give a starttime (&stime=yyyymmddhh24mm). Example: &stime=201310130000&period=86400, will start from 13-10-2013 and show 1 day (86400 seconds)
	curl.setopt(curl.URL, z_url_graph + '?graphid=' + str(graphid) + '&width=1200&height=200&period=604800')
	curl.setopt(curl.WRITEFUNCTION, buffer.write)
	curl.perform()
	f = open(z_image_name, 'wb')
	f.write(buffer.getvalue())
	f.close()

def generateGraphs(hostgroupid):
	try:
		import psycopg2
		import psycopg2.extras # Necessary to generate query results as a dictionary
		pg = psycopg2
	except ImportError:
		print "Module psycopg2 is not installed, please install it!"
		raise
	except:
		print "Error while loading psycopg2 module!"
		raise
	try:
		pg_connection = pg.connect("host='%s' port='%s' dbname='%s' user='%s' password='%s'" % ("10.10.3.8", "9999", "tverdbp01", "mios", "K1HYC0haFBk9jvu71Bpf"))
	except Exception:
		print "Cannot connect to database"
		raise

	pg_cursor = pg_connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
	pg_cursor.execute("select * from mios_report where hostgroupid = %s order by hostname, graphname", (hostgroupid,))
	result = pg_cursor.fetchall()
	pg_cursor.close()
	pg_connection.close()
	return result

def generateReport(hostgroupname, data):
	import docx

	existing_report = 'VermontTemplate.docx' # Leave empty for new file
#	existing_report = ''
	if not existing_report:
		document = docx.newdocument()
	else:
		document = docx.opendocx(existing_report)
	relationships = docx.relationshiplist(existing_report)
	body = document.xpath('/w:document/w:body', namespaces=docx.nsprefixes)[0]
	body.append(docx.heading("MIOS rapportage " + hostgroupname, 1))
	hosts = []
	for record in data:
		if record['hostname'] not in hosts:
			hosts.append(record['hostname'])
	# Performance grafieken
	body.append(docx.heading("Performance grafieken", 2))
	for host in hosts:
		body.append(docx.heading(host, 3))
		for record in data:
			if record['hostname'] == host and record['graphtype'] == 'p':
				getGraph(record['graphid'])
				relationships, picpara = docx.picture(relationships, str(record['graphid']) + '.png', record['graphname'], 450)
				body.append(picpara)
				body.append(docx.caption(record['graphname']))
		body.append(docx.pagebreak(type='page', orient='portrait'))
	# Resource grafieken
	body.append(docx.heading("Resource grafieken", 2))
	for host in hosts:
		body.append(docx.heading(host, 3))
		for record in data:
			if record['hostname'] == host and record['graphtype'] == 'r':
				getGraph(record['graphid'])
				relationships, picpara = docx.picture(relationships, str(record['graphid']) + '.png', record['graphname'], 450)
				body.append(picpara)
				body.append(docx.caption(record['graphname']))
		body.append(docx.pagebreak(type='page', orient='portrait'))

	title = 'MIOS rapportage'
	subject = 'Maandelijkse performance en resources rapportage'
	creator = 'Vermont 24/7'
	keywords = ['MIOS', 'Rapportage', 'Vermont']
	coreprops = docx.coreproperties(title=title, subject=subject, creator=creator, keywords=keywords)
	wordrelationships = docx.wordrelationships(relationships)
	if not existing_report:
		appprops = docx.appproperties()
		contenttypes = docx.contenttypes()
		websettings = docx.websettings()
		docx.savedocx(document, coreprops, appprops, contenttypes, websettings, wordrelationships, 'Rapportage.docx')
	else:
		import shutil, glob
		for file in glob.glob(mreport_home + '/lib/template/word/media/*'):
			shutil.copy2(file, mreport_home + '/tmp/word/media/')
		docx.savedocx(document, coreprops, wordrelationships=wordrelationships, output='Rapportage.docx', template=existing_report)
	import glob # Unix style pathname pattern expansion
	# Remove files which are no longer necessary
	for file in glob.glob(mreport_home + '/*.png'):
		os.remove(file)
	for file in glob.glob(mreport_home + '/lib/template/word/media/*'):
		os.remove(file)
	for root, dirs, files in os.walk(mreport_home + '/tmp/', topdown=False):
		for name in files:
			os.remove(os.path.join(root, name))
		for name in dirs:
			os.rmdir(os.path.join(root, name))

def main():
	# get hostgroup
	hostgroupid, hostgroupname = selectHostgroup()
	os.system('clear')
	# get the hosts and their graphs from selected host group
	result = generateGraphs(hostgroupid)
	generateReport(hostgroupname, result)

if  __name__ == "__main__":
	options, args = get_options()

	zapi = ZabbixAPI(server=options.server,log_level=0)

	try:
		zapi.login(options.username, options.password)
#		print "Zabbix API Version: %s" % zapi.api_version()
	except ZabbixAPIException, e:
		sys.stderr.write(str(e) + '\n')

	main()
