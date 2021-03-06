#!/usr/bin/python
__author__ = "Fabian van der Hoeven"
__copyright__ = "Copyright (C) 2013 Vermont 24x7"
__version__ = "3.2"

import ConfigParser
import sys
import os
import time
import datetime
import logging
import logging.handlers
import logging.config
import re
import calendar
import shutil
import glob  # Unix style pathname pattern expansion

# Add mios-report LIB to path
try:
        mreport_home = os.environ['MREPORT_HOME']
except:
        mreport_home = "/opt/mios/mios-report"
sys.path.append(mreport_home + '/lib')

from zabbix_api import ZabbixAPI, ZabbixAPIException
import GChartWrapper


postgres = None
zapi = None

class Config:
    def __init__(self, conf_file, customer_conf_file):
        self.config = None
        self.customer_config = None
        self.zabbix_frontend = ''
        self.zabbix_user = ''
        self.zabbix_password = ''
        self.postgres_dbname = ''
        self.postgres_dbs = {}
        self.hostgroupid = None
        self.in_test = 0
        self.report_name = ''
        self.report_template = ''
        self.report_start_date = ''
        self.report_period = ''
        self.report_trend_start = ''
        self.report_trend_period = ''
        self.report_graph_width = ''
        self.report_title = ''
        self.report_backup_item = None
        self.report_infra_picture = ''
        self.custom_section = 0
        self.custom_title = ''
        self.table_header_color = ''
        self.table_first_column_color = ''
        try:
            self.mreport_home = os.environ['MREPORT_HOME']
        except:
            self.mreport_home = '/opt/mios/mios-report'

        self.conf_file = conf_file
        self.customer_conf_file = customer_conf_file
        if not os.path.exists(self.conf_file):
            print("Can't open config file %s" % self.conf_file)
            sys.exit(1)
        elif not os.path.exists(self.customer_conf_file):
            print("Can't open config file %s" % self.customer_conf_file)
            sys.exit(1)
        # Read common config
        self.config = ConfigParser.ConfigParser()
        self.config.read(self.conf_file)
        # Read customer specific config
        self.customer_config = ConfigParser.ConfigParser()
        self.customer_config.read(self.customer_conf_file)

    def parse(self):
        # Parse common config
        try:
            self.zabbix_frontend = self.config.get('common', 'zabbix_frontend')
        except:
            self.zabbix_frontend = 'localhost'
        try:
            self.zabbix_user = self.config.get('common', 'zabbix_user')
        except:
            self.zabbix_user = 'admin'
        try:
            self.zabbix_password = self.config.get('common', 'zabbix_password')
        except:
            self.zabbix_password = ''
        try:
            self.postgres_dbname = self.config.get('miosdb', 'dbname')
        except:
            self.postgres_dbname = 'postgres'
        try:
            postgres_host = self.config.get('miosdb', 'host')
        except:
            postgres_host = 'localhost'
        try:
            postgres_port = self.config.get('miosdb', 'port')
        except:
            postgres_port = '5432'
        try:
            postgres_user = self.config.get('miosdb', 'user')
        except:
            postgres_user = 'postgres'
        try:
            postgres_password = self.config.get('miosdb', 'password')
        except:
            postgres_password = 'postgres'
        self.postgres_dbs[self.postgres_dbname] = (postgres_host, postgres_port, postgres_user, postgres_password)
        # Parse e-mail stuff (also common)
        try:
            self.email_sender = self.config.get('email', 'sender')
        except:
            from socket import gethostname
            self.email_sender = 'mios@' + gethostname()
        try:
            self.email_receiver = self.config.get('email', 'receiver')
        except:
            self.email_receiver = ''
        try:
            self.email_server = self.config.get('email', 'server')
        except:
            self.email_server = 'localhost'

        # Parse customer specific config
        try:
            self.hostgroupid = self.customer_config.get('report', 'hostgroupid')
        except:
            self.hostgroupid = None
        try:
            self.in_test = int(self.customer_config.get('report', 'in_test'))
        except:
            self.in_test = 0
        try:
            self.report_name = self.customer_config.get('report', 'name')
        except:
            self.report_name = 'Report.docx'
        try:
            self.report_template = self.customer_config.get('report', 'template')
        except:
            self.report_template = ''
        try:
            self.report_template_language = self.customer_config.get('report', 'lang')
        except:
            self.report_template_language = 'en'
        if 'start_date' not in globals():  # so start_date is not passed as an argument to the script
            try:
                self.report_start_date = self.customer_config.get('report', 'start_date')
                # validate date
                datetime.datetime.strptime(self.report_start_date, '%d-%m-%Y')
            except:
                self.report_start_date = ''
        else:
            self.report_start_date = start_date
        try:
            self.report_period = self.customer_config.get('report', 'period')
            # Convert period to seconds
            match = re.match(r"([0-9]+)([a-z]+)", self.report_period, re.I)
            if match:
                period_items = match.groups()
            if self.report_start_date == '':
                day, month, year = map(int, datetime.date.strftime(datetime.datetime.today(), '%d-%m-%Y').split('-'))
            else:
                day, month, year = map(int, self.report_start_date.split('-'))
            seconds_in_day = 86400
            if period_items[1] == 'd':
                total_seconds = int(period_items[0]) * seconds_in_day
            elif period_items[1] == 'w':
                total_seconds = int(period_items[0]) * 7 * seconds_in_day
            elif period_items[1] == 'm':
                total_seconds = 0
                for next_month in range(int(period_items[0])):
                    if month + next_month > 12:
                        month -= 12
                        year += 1
                    days_in_month = calendar.monthrange(year, month + next_month)[1]
                    total_seconds += days_in_month * seconds_in_day
            elif period_items[1] == 'y':
                if calendar.isleap(year):
                    total_seconds = int(period_items[0]) * 366 * seconds_in_day
                else:
                    total_seconds = int(period_items[0]) * 365 * seconds_in_day
            self.report_period = total_seconds
        except:
            # Defaults to 1 week
            self.report_period = 604800
        # Calculate end_date
        if self.report_start_date != '':
            # If start_date is given calculate end_date with period
            self.report_end_date = datetime.date.strftime(datetime.datetime.strptime(self.report_start_date, "%d-%m-%Y") + datetime.timedelta(seconds=self.report_period - 1), '%d-%m-%Y')
        else:
            # If no start_date is given, assume today as end_date and calculate the start_date with period
            self.report_end_date = datetime.date.strftime(datetime.datetime.today(), '%d-%m-%Y')
            self.report_start_date = datetime.date.strftime(datetime.datetime.strptime(self.report_end_date, "%d-%m-%Y") - datetime.timedelta(seconds=self.report_period - 1), '%d-%m-%Y')

        try:
            self.report_trend_period = self.customer_config.get('report', 'trend_period')
            match = re.match(r"([0-9]+)([a-z]+)", self.report_trend_period, re.I)
            if match:
                period_items = match.groups()
            seconds_in_day = 86400
            if period_items[1] == 'm':
                day, month, year = map(int, self.report_start_date.split('-'))
                month -= int(period_items[0])
                month += 1
                if month < 1:
                    month += 12
                    year -= 1
                total_seconds = 0
                self.report_trend_start = str(day).zfill(2) + '-' + str(month).zfill(2) + '-' + str(year).zfill(2)
                for next_month in range(int(period_items[0])):
                    if month + next_month > 12:
                        month -= 12
                        year += 1
                    days_in_month = calendar.monthrange(year, month + next_month)[1]
                    total_seconds += days_in_month * seconds_in_day
            self.report_trend_period = total_seconds
        except:
            self.report_trend_period = self.report_period
        try:
            self.report_graph_width = self.customer_config.get('report', 'graph_width')
        except:
            self.report_graph_width = '1200'
        try:
            self.report_title = self.customer_config.get('report', 'title')
        except:
            self.report_title = "Zabbix rapportage"
        try:
            self.report_backup_item = self.customer_config.get('report', 'backup_item')
        except:
            self.report_backup_item = None
        try:
            self.report_infra_picture = self.customer_config.get('report', 'infra_picture')
        except:
            self.report_infra_picture = None
        try:
            self.custom_section = int(self.customer_config.get('report', 'custom'))
        except:
            self.custom_section = 0
        if self.custom_section == 1:
            try:
                self.custom_title = self.customer_config.get('report', 'custom_title')
            except:
                self.custom_title = "None specified"
        try:
            self.table_header_color = self.customer_config.get('report', 'table_header_color')
        except:
            self.table_header_color = config.table_header_color
        try:
            self.table_first_column_color = self.customer_config.get('report', 'table_first_column_color')
        except:
            self.table_first_column_color = config.table_first_column_color

class Postgres(object):
    def __init__(self, instances):
        self.postgres_support = 0
        self.connections = []
        self.cursor = []
        self.version = []
        self.host = []
        self.port = []
        self.user = []
        self.password = []
        self.dbs = []
        self.instances = instances
        self.logger = logging.getLogger(type(self).__name__)

        try:
            import psycopg2
            import psycopg2.extras
            self.psycopg2 = psycopg2
            self.psycopg2_extras = psycopg2.extras
            self.postgres_support = 1
            self.logger.info("Successfully loaded psycopg2 module")
        except ImportError:
            self.logger.error("Module psycopg2 is not installed, please install it!")
            raise
        except:
            self.logger.error("Error while loading psycopg2 module!")
            raise

        if self.postgres_support == 0:
            return None

        for instance in instances:
            host, port, user, password = instances[instance]
            self.host.append(host)
            self.port.append(port)
            self.user.append(user)
            self.password.append(password)
            self.dbs.append(instance)
            self.connections.append(None)
            self.cursor.append(None)
            self.version.append('')
            indx = self.dbs.index(instance)
            self.connect(indx)

    def connect(self, indx):
        while self.connections[indx] is None:
            try:
                self.connections[indx] = self.psycopg2.connect("host='%s' port='%s' dbname='%s' user='%s' password='%s'" % (self.host[indx], self.port[indx], self.dbs[indx], self.user[indx], self.password[indx]))
                self.logger.info("Connection succesful (%s)" % self.dbs[indx])
            except Exception as e:
                self.logger.critical("Unable to connect to Postgres")
                self.logger.critical("PG: Additional information: %s" % e)
                self.logger.info("Trying to reconnect in 10 seconds")
                time.sleep(10)
        self.cursor[indx] = self.connections[indx].cursor(cursor_factory=self.psycopg2_extras.DictCursor)
        self.cursor[indx].execute('select version()')
        self.version[indx] = self.cursor[indx].fetchone()
        self.logger.info("Connect to Postgres version %s DB: %s" % (self.version[indx], self.dbs[indx]))

    def execute(self, db, query):
        if self.postgres_support == 0:
            self.logger.error("Postgres not supported")
            return None

        if not db in self.dbs:
            return -1
        try:
            indx = self.dbs.index(db)
            try:
                self.cursor[indx].execute(query)
            except Exception as e:
                self.logger.error("PG: Failed to execute query: %s" % query)
                self.logger.error("PG: Additional info: %s" % e)
                return -1

            try:
                value = self.cursor[indx].fetchall()
            except Exception as e:
                self.logger.error("PG: Failed to fetch resultset")
                self.logger.error("PG: Additional info: %s" % e)
                return -1

            self.logger.debug("Query executed: %s" % query)
            self.logger.debug("Query result  : %s" % str(value))
            return value
        except:
            self.logger.critical("Error in Postgres connection DB: %s" % db)
            return -2

def my_logger(log_text, loglevel='info'):
    rootLogger = logging.getLogger()
    method_caller = sys._getframe().f_back.f_code.co_name
    loglevels = {
        "CRITICAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "INFO": 20,
        "DEBUG": 10
    }

    if loglevel.upper() not in loglevels:
        print "Invalid loglevel '%s'" % loglevel
        print "Method caller: %s" % method_caller
        print "Valid loglevels are:"
        for key, value in loglevels.iteritems():
            print ' - %s' % key
        print "\n loglevels are case insensitive"
        sys.exit(1)
    rootLogger.log(loglevels[loglevel.upper()], "%s - %s" % (method_caller, log_text))

def select_hostgroup():
    teller = 0
    hostgroups = {}
    for hostgroup in zapi.hostgroup.get({"output": "extend", "filter": {"internal": "0"}}):
        teller += 1
        hostgroups[teller] = (hostgroup['name'], hostgroup['groupid'])
        my_logger('Fetching hostgroups via API', 'info')
        my_logger("Fetched hostgroups: %s" % hostgroups, 'debug')
    hostgroupid = -1
    while hostgroupid == -1:
        os.system('clear')
        print("Hostgroups:")
        for hostgroup in hostgroups:
            print('\t%2d: %s (hostgroupid: %s)' % (hostgroup, hostgroups[hostgroup][0], hostgroups[hostgroup][1]))
        try:
            hostgroupnr = int(raw_input('Select hostgroup: '))
            my_logger("Raw input: %s" % hostgroupnr, 'debug')
            try:
                hostgroupid = hostgroups[hostgroupnr][1]
                hostgroupname = hostgroups[hostgroupnr][0]
            except KeyError:
                my_logger('Raw input out of range, try again', 'error')
                print("\nCounting is not your greatest asset!")
                hostgroupid = -1
                print("\nPress a key to try again...")
                os.system('read -N 1 -s')
        except ValueError:
            my_logger('Raw input not a number, try again', 'error')
            print("\nEeuhm... I don't think that's a number!")
            hostgroupid = -1
            print("\nPress a key to try again...")
            os.system('read -N 1 -s')
        except KeyboardInterrupt:  # Catch CTRL-C
            pass
    my_logger("Hostgroup selected (hostgroupid: %s, hostgroupname: %s)" % (hostgroupid, hostgroupname), 'info')
    return (hostgroupid, hostgroupname)

def get_hostgroup_name(hostgroupid):
    try:
        my_logger('Fetching hostgroupname via API', 'info')
        hostgroupname = zapi.hostgroup.get({"output": "extend", "filter": {"groupid": hostgroupid}})[0]['name']
    except Exception as e:
        my_logger('Fetching hostgroupname via API failed', 'error')
        my_logger("Additional info: %s" % e, 'error')
        hostgroupname = 0
    return hostgroupname

def check_hostgroup_graphs(hostgroupid):
    my_logger("Checking if graphs for this hostgroupid (%s) are configured" % hostgroupid, 'debug')
    num_graphs_host = postgres.execute(config.postgres_dbname, "select count(*) from mios_report_graphs where hostgroupid = %s" % hostgroupid)
    num_items_host = postgres.execute(config.postgres_dbname, "select count(*) from mios_report_uptime where hostgroupid = %s" % hostgroupid)
    if int(num_graphs_host[0][0]) > 0:
        my_logger("Found graphs for hostgroupid (%s)" % hostgroupid, 'debug')
        result = 1
    elif int(num_items_host[0][0]) > 0:
        my_logger("Found uptime items for hostgroupid (%s)" % hostgroupid, 'debug')
        result = 1
    else:
        my_logger("Didn't find graphs or uptime items for hostgroupid (%s)" % hostgroupid, 'error')
        result = 0
    return result

def get_graph(graphid, graphtype):
    import pycurl
    import StringIO
    curl = pycurl.Curl()
    buffer = StringIO.StringIO()

    z_server = config.zabbix_frontend
    z_user = config.zabbix_user
    z_password = config.zabbix_password
    z_url_index = z_server + 'index.php'
    z_url_graph = z_server + 'chart2.php'
    z_login_data = 'name=' + z_user + '&password=' + z_password + '&autologon=1&enter=Sign+in'
    # When we leave the filename of the cookie empty, curl stores the cookie in memory
    # so now the cookie doesn't have to be removed after usage. When the script finishes, the cookie is also gone
    z_filename_cookie = ''
    z_image_name = mreport_home + '/' + str(graphid) + '_' + graphtype + '.png'
    # Log on to Zabbix and get session cookie
    my_logger('Logging on to Zabbix and retrieving cookie', 'debug')
    curl.setopt(curl.URL, z_url_index)
    curl.setopt(curl.POSTFIELDS, z_login_data)
    curl.setopt(curl.COOKIEJAR, z_filename_cookie)
    curl.setopt(curl.COOKIEFILE, z_filename_cookie)
    curl.setopt(curl.SSL_VERIFYPEER, 0)
    curl.perform()
    # Retrieve graphs using cookie
    # By just giving a period the graph will be generated from today and "period" seconds ago. So a period of 604800 will be 1 week (in seconds)
    # You can also give a starttime (&stime=yyyymmddhh24mm). Example: &stime=201310130000&period=86400, will start from 13-10-2013 and show 1 day (86400 seconds)
    if graphtype == 't':  # trending graph
        my_logger('Fetching trending graph', 'info')
        day, month, year = config.report_trend_start.split('-')
        stime = year + month + day + '000000'
        my_logger("graphid: %s, width: %s, stime: %s, period: %s" % (str(graphid), config.report_graph_width, stime, str(config.report_trend_period)), 'info')
        curl.setopt(curl.URL, z_url_graph + '?graphid=' + str(graphid) + '&width=' + config.report_graph_width + '&stime=' + stime + '&period=' + str(config.report_trend_period) + '&isNow=0')
    else:  # normal graph
        my_logger('Fetching normal graph', 'info')
        day, month, year = config.report_start_date.split('-')
        stime = year + month + day + '000000'
        my_logger("graphid: %s, width: %s, stime: %s, period: %s" % (str(graphid), config.report_graph_width, stime, str(config.report_period)), 'info')
        curl.setopt(curl.URL, z_url_graph + '?graphid=' + str(graphid) + '&width=' + config.report_graph_width + '&stime=' + stime + '&period=' + str(config.report_period) + '&isNow=0')
    curl.setopt(curl.WRITEFUNCTION, buffer.write)
    curl.perform()
    f = open(z_image_name, 'wb')
    f.write(buffer.getvalue())
    my_logger("Writing image: %s" % z_image_name, 'debug')
    f.close()

def convert_interval(interval):
    #Converts an interval like 5m to 300 (seconds)
    multiplier = 1
    try:
        interval = int(interval)
    except ValueError:
        interval_time = interval[-1]
        interval = int(interval[:-1])
        if interval_time == 'm':
            multiplier = 60
        elif interval_time == 'h':
            multiplier = 3600
    return (interval * multiplier)

def get_uptime_graph(itemid):
    my_logger('Fetching uptime graphs', 'info')
    day, month, year = map(int, config.report_start_date.split('-'))

    start_epoch = int(time.mktime((year, month, day, 0, 0, 0, 0, 0, 0)))
    end_epoch = start_epoch + config.report_period
    my_logger("Fetching total polling items for item: %s, epoch between %s and %s" % (itemid, start_epoch, end_epoch), 'info')
    polling_total = postgres.execute(config.postgres_dbname, "select count(*) from history_uint where itemid = %s and clock between %s and %s" % (itemid, start_epoch, end_epoch))[0][0]
    my_logger("Total polling items for item: %s, %s" % (itemid, polling_total), 'debug')
    my_logger("Fetching clocks for downtime, item: %s, epoch between %s and %s" % (itemid, start_epoch, end_epoch), 'info')
    rows = postgres.execute(config.postgres_dbname, "select clock from history_uint where itemid = %s and clock > %s and clock < %s and value = 0 order by clock" % (itemid, start_epoch, end_epoch))
    my_logger("Clocks for downtime for item: %s, %s" % (itemid, rows), 'debug')
    polling_down_rows = []
    for row in rows:
        polling_down_rows.append(row[0])
    my_logger("Fetching maintenance periods for item: %s, epoch between %s and %s" % (itemid, start_epoch, end_epoch), 'info')
    item_maintenance_rows = postgres.execute(config.postgres_dbname, "select start_date, (start_date + period) from timeperiods\
     inner join maintenances_windows on maintenances_windows.timeperiodid = timeperiods.timeperiodid\
     inner join maintenances on maintenances.maintenanceid = maintenances_windows.maintenanceid\
     inner join maintenances_groups on maintenances_groups.maintenanceid = maintenances.maintenanceid\
     inner join groups on maintenances_groups.groupid = groups.groupid\
     inner join hosts_groups on hosts_groups.groupid = groups.groupid\
     inner join hosts on hosts_groups.hostid = hosts.hostid\
     inner join items on items.hostid = hosts.hostid\
     where items.itemid = %s and timeperiods.start_date between %s and %s" % (itemid, start_epoch, end_epoch))
    my_logger("Maintenance periods for item: %s, %s" % (itemid, item_maintenance_rows), 'debug')
    polling_down_maintenance = []
    polling_down = list(polling_down_rows)  # Make copy of list so that it can be edited without affecting original list (mutable), same as polling_down_rows[:]
    my_logger('Check if downtime was in maintenance', 'info')
    for clock in polling_down_rows:
        for mclock in item_maintenance_rows:
            if mclock[0] <= clock <= mclock[1]:
                # Is down clock between maintenance period?
                # Then add to down_maintenance and remove from down
                polling_down_maintenance.append(clock)
                polling_down.remove(clock)

    my_logger("Fetch item interval for item: %s" % itemid, 'info')
    item_interval = postgres.execute(config.postgres_dbname, "select delay from items where itemid = %s" % itemid)[0][0]
    my_logger("Item interval for item: %s, %s" % (itemid, item_interval), 'debug')
    item_interval = convert_interval(item_interval)
    # Get history values which have no data for longer then the interval and at least a couple of seconde more then the interval
    interval_threshold = item_interval + int(item_interval/2)
    my_logger("Fetching clocks with consecutive downtime larger then threshold for item: %s" % itemid, 'info')
    rows = postgres.execute(config.postgres_dbname, "select clock, difference from\
     (\
      select clock, clock - lag(clock) over (order by clock) as difference from history_uint\
      where itemid = %s and clock between %s and %s\
     ) t\
     where difference > %s" % (itemid, start_epoch, end_epoch, interval_threshold))
    my_logger("Clocks with consecutive downtime for item: %s, %s" % (itemid, rows), 'debug')
    item_nodata_rows = []
    for row in rows:
        end_date_nodata = row[0]
        seconds_nodata = row[1]
        start_date_nodata = end_date_nodata - seconds_nodata
        item_nodata_rows.append((start_date_nodata, end_date_nodata))
    item_nodata_maintenance = []
    item_nodata = list(item_nodata_rows)  # Make copy of list so that it can be edited without affecting original list (mutable), same as item_nodata_rows[:]
    for clock in item_nodata_rows:  # Check if the nodata items are within maintenance window
        for mclock in item_maintenance_rows:
            if mclock[0] <= clock[0] <= mclock[1]:
                item_nodata_maintenance.append(clock)
                item_nodata.remove(clock)
    num_pollings_nodata = 0
    num_pollings_nodata_maintenance = 0
    for item in item_nodata_maintenance:  # Count items with nodata but within maintenance
        seconds_nodata = item[1] - item[0]
        num_pollings_nodata_maintenance += (seconds_nodata / item_interval)
    for item in item_nodata:  # Count items with nodata but not in maintenance
        seconds_nodata = item[1] - item[0]
        num_pollings_nodata += (seconds_nodata / item_interval)
    my_logger('', 'info')
    my_logger("Summary for item: %s" % itemid, 'info')
    my_logger("Polling items with nodata and in maintenance        : %s" % num_pollings_nodata_maintenance, 'info')
    my_logger("Polling items with nodata and NOT in maintenance    : %s" % num_pollings_nodata, 'info')
    my_logger("Polling items down and in maintenance               : %s" % len(polling_down_maintenance), 'info')
    my_logger("Polling items down and NOT in maintenance           : %s" % len(polling_down), 'info')
    my_logger("Polling items UP                                    : %s" % (polling_total - len(polling_down_maintenance) - len(polling_down)), 'info')
    my_logger("Start epoch                                         : %s" % start_epoch, 'info')
    my_logger("Eind epoch                                          : %s" % end_epoch, 'info')
    my_logger("Period in seconds                                   : %s" % config.report_period, 'info')

    try:
        percentage_down_maintenance = (float(len(polling_down_maintenance) + num_pollings_nodata_maintenance) / float(polling_total)) * 100
    except ZeroDivisionError:
        percentage_down_maintenance = 0
    try:
        percentage_down = (float(len(polling_down) + num_pollings_nodata) / float(polling_total)) * 100
        if percentage_down > 100:
            percentage_down = 100
    except ZeroDivisionError:
        percentage_down = 0
    percentage_up = 100 - (percentage_down + percentage_down_maintenance)
    if percentage_up < 0:
        percentage_up = 0
    my_logger("Percentage down and in maintenanve during period    : %s" % percentage_down_maintenance, 'info')
    my_logger("Percentage down and NOT in maintenance during period: %s" % percentage_down, 'info')
    my_logger("Percentage up during period                         : %s" % percentage_up, 'info')
    my_logger('', 'info')

    my_logger("Fetching pie chart using Google GChartWrapper.Pie3D API for item: %s" % itemid, 'info')
    uptime_graph = GChartWrapper.Pie3D([percentage_up, percentage_down, percentage_down_maintenance])
    uptime_graph.size(400, 100)
    uptime_graph.label('Up (%.2f%%)' % percentage_up, 'Down (%.2f%%)' % percentage_down, 'Maintenance (%.2f%%)' % percentage_down_maintenance)
    uptime_graph.color('00dd00', 'dd0000', 'ff8800')
    uptime_graph.save(mreport_home + '/' + str(itemid) + '.png')

    # Generate table overview of down time (get consecutive down periods)
    my_logger("Generate downtime rows to be displayed in Word as table for item: %s" % itemid, 'info')
    item_interval *= 2  # Double interval. Interval is never exact. Allways has a deviation of 1 or 2 seconds. So we double the interval just to be safe
    my_logger("Doubling interval for item: %s. Interval is never exact. Allways a deviation of a couple of seconds. So double it just to be safe" % itemid, 'info')
    my_logger("New interval for itemid: %s, %s" % (itemid, item_interval), 'info')
    downtime_periods = []
    polling_down_rows.sort()  # Sort the list to get consecutive downtimes
    if len(polling_down_rows) > 0:
        for num in range(len(polling_down_rows)):
            if num == 0:
                start_period = polling_down_rows[num]
                prev_clock = start_period
                end_period = start_period + item_interval
            else:
                if polling_down_rows[num] <= prev_clock + item_interval:
                    # Consecutive down time
                    end_period = polling_down_rows[num]
                    prev_clock = polling_down_rows[num]
                else:
                    end_period = start_period + item_interval
                    downtime_periods.append((start_period, end_period))
                    start_period = polling_down_rows[num]
                    prev_clock = polling_down_rows[num]
        downtime_periods.append((start_period, end_period))
    # Append nodata rows to downtime_periods
    for nodata_rows in item_nodata_rows:
        downtime_periods.append(nodata_rows)
    try:
        downtime_periods = list(merge_tuples_epoch_times(downtime_periods))
    except:
        pass
    my_logger("Downtime periods: %s" % downtime_periods, 'debug')
    return (downtime_periods, percentage_up, percentage_down, percentage_down_maintenance)


def merge_tuples_epoch_times(times):
    saved = list(times[0])
    for st, en in sorted([sorted(t) for t in times]):
        if st <= saved[1]:
            saved[1] = max(saved[1], en)
        else:
            yield tuple(saved)
            saved[0] = st
            saved[1] = en
    yield tuple(saved)


def get_maintenance_periods(hostgroupid):
    day, month, year = map(int, config.report_start_date.split('-'))
    start_epoch = int(time.mktime((year, month, day, 0, 0, 0, 0, 0, 0)))
    end_epoch = start_epoch + config.report_period
    my_logger("Fetching maintenance rows for hostgroupid: %s, epoch between %s and %s" % (hostgroupid, start_epoch, end_epoch), 'info')
    maintenance_rows = postgres.execute(config.postgres_dbname, "select maintenances.name || '. ' || maintenances.description, start_date, (start_date + period) from timeperiods\
     inner join maintenances_windows on maintenances_windows.timeperiodid = timeperiods.timeperiodid\
     inner join maintenances on maintenances.maintenanceid = maintenances_windows.maintenanceid\
     inner join maintenances_groups on maintenances_groups.maintenanceid = maintenances.maintenanceid\
     inner join groups on maintenances_groups.groupid = groups.groupid\
     where groups.groupid = %s and timeperiods.start_date between %s and %s" % (hostgroupid, start_epoch, end_epoch))
    my_logger("Maintenance rows: %s" % maintenance_rows, 'debug')
    return maintenance_rows


def get_graphs_list(hostgroupid):
    my_logger("Fetching graphs list for hostgroup (%s)" % hostgroupid, 'info')
    return postgres.execute(config.postgres_dbname, "select * from mios_report_graphs where hostgroupid = %s order by hostname, graphname" % hostgroupid)


def get_items_list(hostgroupid):
    my_logger("Fetching uptime items for hostgroup (%s)" % hostgroupid, 'info')
    return postgres.execute(config.postgres_dbname, "select * from mios_report_uptime where hostgroupid = %s order by hostname, itemname" % hostgroupid)


def get_backup_list(itemid):
    day, month, year = map(int, config.report_start_date.split('-'))

    start_epoch = int(time.mktime((year, month, day, 0, 0, 0, 0, 0, 0)))
    end_epoch = start_epoch + config.report_period

    if config.in_test:
        my_logger('In test mode. Using fixed backuplist', 'info')
        backupList = [['15-11-2013 00:59:03;15-11-2013 01:10:15;00:11:12;COMPLETED;DB FULL'], ['14-11-2013 00:59:03;14-11-2013 01:10:15;00:11:12;COMPLETED;DB FULL']]
    else:
        my_logger('Not in test mode. Fetching backuplist from database', 'info')
        backupList = postgres.execute(config.postgres_dbname, "select value from history_text where itemid = %s and clock between %s and %s order by clock" % (itemid, start_epoch, end_epoch))
    return backupList


def get_db_text(hostgroupid, paragraphName):
    paragraphText = postgres.execute(config.postgres_dbname, "select paragraph_text from mios_report_text where hostgroupid = %s and paragraph_name = '%s'" % (hostgroupid, paragraphName))
    if not paragraphText:
        my_logger("No paragraph_text found for hostgroup %s and paragraph_name '%s'. Fetching defaults." % (get_hostgroup_name(hostgroupid), paragraphName), 'warning')
        paragraphText = postgres.execute(config.postgres_dbname, "select paragraph_text from mios_report_text where hostgroupid = 0 and paragraph_name = '%s'" % paragraphName)
        if not paragraphText:
            my_logger("No default paragraph found for paragraph_name '%s'. Returning empty string" % paragraphName, 'warning')
            return ''
    return paragraphText[0][0]


def get_replace_strings(hostgroupid):
    db_text = get_db_text(hostgroupid, 'Replace_strings').split('\n')
    return dict(map(str.strip, line.split('=')) for line in db_text)


def send_report(filename, hostgroupname):
    import smtplib
    from email.MIMEMultipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.MIMEBase import MIMEBase
    from email import Encoders

    sender = config.email_sender
    receiver = config.email_receiver

    msg = MIMEMultipart()
    text = 'Bij deze de rapportage van %s van de periode %s t/m %s' % (hostgroupname, config.report_start_date, config.report_end_date)
#   html = """\
#       <html>
#           <head></head>
#               <body>
#                   %s
#               </body>
#       </html>
#   """ % text
    body = MIMEMultipart('alternative')
    part1 = MIMEText(text, 'plain')
#   part2 = MIMEText(html, 'html')
    body.attach(part1)
#   body.attach(part2)
    msg.attach(body)

    attachFile = MIMEBase('application', 'msword')
    attachFile.set_payload(file(filename).read())
    Encoders.encode_base64(attachFile)
    attachFile.add_header('Content-Disposition', 'attachment', filename=os.path.basename(filename))
    msg.attach(attachFile)
    msg['Subject'] = 'Rapportage %s, %s t/m %s' % (hostgroupname, config.report_start_date, config.report_end_date)
    msg['From'] = 'Zabbix report <%s>' % sender
    msg['To'] = receiver
    my_logger("Mailing report to %s" % receiver, 'info')
    mailer = smtplib.SMTP(config.email_server)
    mailer.sendmail(sender, receiver, msg.as_string())
    mailer.quit()


def generate_report(hostgroupid, hostgroupname, graphData, itemData):
    import docx

    my_logger('Starting report generation', 'info')
    if config.report_template == '':
        existing_report = ''
        my_logger('Using the default docx template', 'info')
    else:
        existing_report = config.mreport_home + '/templates/' + config.report_template
        my_logger("Using the specified template: %s" % existing_report, 'info')
    if not existing_report:
        document = docx.newdocument()
        my_logger('Creating new document', 'debug')
    else:
        document = docx.opendocx(existing_report, mreport_home + '/tmp')
        my_logger("Opening existing document: %s" % existing_report, 'debug')
    relationships = docx.relationshiplist(existing_report, mreport_home + '/tmp')
    body = document.xpath('/w:document/w:body', namespaces=docx.nsprefixes)[0]
    # Samenvatting toevoegen met maintenance overzicht in opmerkingen
    body.append(docx.heading("Samenvatting", 1, lang=config.report_template_language))
    body.append(docx.heading("Opmerkingen", 2, lang=config.report_template_language))
    # Maintenance tabel
    maintenance_periods = get_maintenance_periods(hostgroupid)
    maintenance_tbl_rows = []
    tbl_heading = ['OMSCHRIJVING', 'START MAINTENANCE', 'EINDE MAINTENANCE', 'DUUR']
    maintenance_tbl_rows.append(tbl_heading)
    if len(maintenance_periods) > 0:
        for num in range(len(maintenance_periods)):
            tbl_row = []
            (description, start_period, end_period) = maintenance_periods[num]
            tbl_row.append(description)
            tbl_row.append(datetime.datetime.fromtimestamp(start_period).strftime("%d-%m-%Y %H:%M:%S"))
            tbl_row.append(datetime.datetime.fromtimestamp(end_period).strftime("%d-%m-%Y %H:%M:%S"))
            tbl_row.append(dhms(end_period - start_period))
            maintenance_tbl_rows.append(tbl_row)
            body.append(docx.table(maintenance_tbl_rows, headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))
    else:
        tbl_rows = []
        tbl_heading = ['ITEM', 'OPMERKINGEN']
        tbl_rows.append(tbl_heading)
        tbl_rows.append(['', ''])
        body.append(docx.table(tbl_rows, colw=[1188, 7979], headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))

    body.append(docx.heading("Aktiepunten", 2, lang=config.report_template_language))

    body.append(docx.heading("Monitoring", 1, lang=config.report_template_language))
    #Custom section
    #First check if a custom section is configured
    if config.custom_section == 1:
        #Then generate custom chapter
        body.append(docx.heading(config.custom_title, 2, lang=config.report_template_language))
        body.append(docx.paragraph(get_db_text(hostgroupid, 'Custom')))
        for record in graphData:
            if record['graphtype'] == 'c':
                my_logger("Generating custom graph '%s'" % record['graphname'], 'info')
                get_graph(record['graphid'], 'c')
                body.append(docx.heading(record['graphname'], 3, lang=config.report_template_language))
                try:
                    relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_c.png', record['graphname'], 450)
                except:
                    my_logger('Reading graph image file failed. Possible timing issue. Retry in 2 seconds', 'warning')
                    time.sleep(2)  # Timing issues can occur when get_graph is writing image and docx.picture tries to read image
                    relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_c.png', record['graphname'], 450)
                body.append(picpara)
                body.append(docx.figureCaption(record['graphname'], lang=config.report_template_language))
    body.append(docx.heading("Beschikbaarheid business services", 2, lang=config.report_template_language))
    body.append(docx.paragraph(get_db_text(hostgroupid, 'Beschikbaarheid_business_services')))

    num_web_check_found = 0
    for record in graphData:
        if record['graphtype'] == 'w':
            num_web_check_found += 1
            my_logger("Generating web-check graph '%s'" % record['graphname'], 'info')
            get_graph(record['graphid'], 'w')
            try:
                relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_w.png', record['graphname'], 450)
            except:
                my_logger('Reading graph image file failed. Possible timing issue. Retry in 2 seconds', 'warning')
                time.sleep(2)  # Timing issues can occur when get_graph is writing image and docx.picture tries to read image
                relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_w.png', record['graphname'], 450)
            if num_web_check_found == 1:
                body.append(docx.heading("Web-check", 3, lang=config.report_template_language))
            body.append(picpara)
            body.append(docx.figureCaption(record['graphname'], lang=config.report_template_language))
    hosts = []
    for record in graphData:  # Create list of hosts for iteration
        if record['hostname'] not in hosts:
            hosts.append(record['hostname'])
    uptime_items = []
    for record in itemData:  # Create list of uptime items for iteration
        if record['itemname'] not in uptime_items:
            uptime_items.append(record['itemname'])

    body.append(docx.heading("Beschikbaarheid business componenten", 2, lang=config.report_template_language))
    body.append(docx.paragraph(get_db_text(hostgroupid, 'Beschikbaarheid_business_componenten')))
    body.append(docx.paragraph(''))
    tbl_rows = []
    tbl_heading = ['VPN', 'Percentage down', 'Percentage down - maintenance', 'Percentage up']
    tbl_rows.append(tbl_heading)

    for item in uptime_items:
#        body.append(docx.heading(item, 3, lang=config.report_template_language))
        for record in itemData:
            if record['itemname'] == item:
#                my_logger("Generating uptime graph '%s' from item '%s'" % (record['itemname'], item), 'info')
                my_logger("Generating uptime table_row '%s' from item '%s'" % (record['itemname'], item), 'info')
                (downtime_periods, percentage_up, percentage_down, percentage_down_maintenance) = get_uptime_graph(record['itemid'])
#                try:
#                    relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['itemid']) + '.png', record['itemname'], 200, jc='center')
#                except:
#                    my_logger('Reading graph image file failed. Possible timing issue. Retry in 2 seconds', 'warning')
#                    time.sleep(2)  # Timing issues can occur when get_graph is writing image and docx.picture tries to read image
#                    relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['itemid']) + '.png', record['itemname'], 200, jc='center')
#                body.append(picpara)
#                body.append(docx.figureCaption(record['hostname'] + '-' + record['itemname'], lang=config.report_template_language))
#                tbl_heading = ['START DOWNTIME', 'EINDE DOWNTIME', 'DUUR']
#                for num in range(len(downtime_periods)):
#                    tbl_row = []
#                    (start_period, end_period) = downtime_periods[num]
#                    tbl_row.append(datetime.datetime.fromtimestamp(start_period).strftime("%d-%m-%Y %H:%M:%S"))
#                    tbl_row.append(datetime.datetime.fromtimestamp(end_period).strftime("%d-%m-%Y %H:%M:%S"))
#                    tbl_row.append(dhms(end_period - start_period))
#                    tbl_rows.append(tbl_row)
#                if len(downtime_periods) > 0:
#                    body.append(docx.table(tbl_rows, headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))
                tbl_row = []
                uptime_item_name = record['itemname']
                replace_strings = get_replace_strings(hostgroupid)
                for string, replace_by in replace_strings.items():
                    uptime_item_name = uptime_item_name.replace(string, replace_by)
                tbl_row.append(uptime_item_name)
                tbl_row.append('%.2f' % percentage_down)
                tbl_row.append('%.2f' % percentage_down_maintenance)
                tbl_row.append('%.2f' % percentage_up)
                tbl_rows.append(tbl_row)
    body.append(docx.table(tbl_rows, headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))
    # Maintenance periodes
    body.append(docx.heading("Maintenance-overzicht", 3, lang=config.report_template_language))
    # De gegevens zijn al gegenereerd bij de samenvatting. Dus er hoeft alleen nog maar gekeken te worden of het nogmaals toegevoegd moet worden
    if len(maintenance_periods) > 0:
        body.append(docx.table(maintenance_tbl_rows, headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))
    else:
        body.append(docx.paragraph("Er is in de afgelopen periode geen gepland onderhoud geweest."))

    body.append(docx.heading("Opmerkingen", 3, lang=config.report_template_language))
    tbl_rows = []
    tbl_heading = ['ITEM', 'OPMERKINGEN']
    tbl_rows.append(tbl_heading)
    tbl_rows.append(['', ''])
    body.append(docx.table(tbl_rows, colw=[1188, 7979], headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))

    # Performance grafieken
    body.append(docx.heading("Basic performance counters", 2, lang=config.report_template_language))
    body.append(docx.paragraph(get_db_text(hostgroupid, 'Basic_performance_counters')))
    points = ['CPU-load: geeft de zogenaamde "load averages" van een systeem weer. Dit getal is de som van het aantal wachtende processen + actieve processen op de CPU;',
              'CPU utilization: dit getal geeft aan hoeveel procent van de CPU-capaciteit daadwerkelijk wordt gebruikt per tijdseenheid, onderverdeeld naar type CPU-gebruik;',
              'Memory utilization: dit getal geeft aan hoeveel memory er op de server in gebruik is, onderverdeeld naar type memory-gebruik;',
              'Disk stats: geeft latency aan van relevante disken;',
              'Network traffic: geeft network-gebruik aan.']
    for point in points:
        body.append(docx.paragraph(point, style='ListBulleted'))
    body.append(docx.paragraph("De grafieken zijn gegroepeerd naar server, dit geeft het beste inzicht in de specifieke server."))
    body.append(docx.pagebreak(type='page', orient='portrait'))
    for host in hosts:
        host_has_graphs = 0
        for record in graphData:
            if record['hostname'] == host and (record['graphtype'] == 'p' or record['graphtype'] == 'r'):
                host_has_graphs = 1
        if host_has_graphs:
            body.append(docx.heading(host, 3, lang=config.report_template_language))
            for record in graphData:
                if record['hostname'] == host and (record['graphtype'] == 'p' or record['graphtype'] == 'r'):
                    my_logger("Generating performance graph '%s' from host '%s'" % (record['graphname'], host), 'info')
                    get_graph(record['graphid'], 'p')
                    try:
                        relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_p.png', record['graphname'], 450)
                    except:
                        my_logger('Reading graph image file failed. Possible timing issue. Retry in 2 seconds', 'warning')
                        time.sleep(2)  # Timing issues can occur when get_graph is writing image and docx.picture tries to read image
                        relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_p.png', record['graphname'], 450)
                    body.append(picpara)
                    body.append(docx.figureCaption(record['graphname'], lang=config.report_template_language))
#           body.append(docx.pagebreak(type='page', orient='portrait'))

    body.append(docx.heading("Opmerkingen", 3, lang=config.report_template_language))
    tbl_rows = []
    tbl_heading = ['ITEM', 'OPMERKINGEN']
    tbl_rows.append(tbl_heading)
    tbl_rows.append(['', ''])
    body.append(docx.table(tbl_rows, colw=[1188, 7979], headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))

    # Trending grafieken
    body.append(docx.heading("Trending", 2, lang=config.report_template_language))
    body.append(docx.paragraph(get_db_text(hostgroupid, 'Trending')))
    for host in hosts:
        host_has_graphs = 0
        for record in graphData:
            if record['hostname'] == host and (record['graphtype'] == 't' or record['graphtype'] == 'r'):
                host_has_graphs = 1
        if host_has_graphs:
            body.append(docx.heading(host, 3, lang=config.report_template_language))
            for record in graphData:
                if record['hostname'] == host and (record['graphtype'] == 't' or record['graphtype'] == 'r'):
                    my_logger("Generating trending graph '%s' from host '%s'" % (record['graphname'], host), 'info')
                    get_graph(record['graphid'], 't')
                    try:
                        relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_t.png', record['graphname'], 450)
                    except:
                        my_logger('Reading graph image file failed. Possible timing issue. Retry in 2 seconds', 'warning')
                        time.sleep(2)  # Timing issues can occur when get_graph is writing image and docx.picture tries to read image
                        relationships, picpara = docx.picture(relationships, mreport_home + '/' + str(record['graphid']) + '_t.png', record['graphname'], 450)
                    body.append(picpara)
                    body.append(docx.figureCaption(record['graphname'], lang=config.report_template_language))

    body.append(docx.heading("Opmerkingen", 3, lang=config.report_template_language))
    tbl_rows = []
    tbl_heading = ['ITEM', 'OPMERKINGEN']
    tbl_rows.append(tbl_heading)
    tbl_rows.append(['', ''])
    body.append(docx.table(tbl_rows, colw=[1188, 7979], headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))

#    body.append(docx.heading("Advanced performance counters", 2, lang=config.report_template_language))
#    body.append(docx.paragraph(get_db_text(hostgroupid, 'Advanced_performance_counters')))
#    my_logger('Done generating graphs...', 'info')

    # Backup overzicht
#    body.append(docx.heading("Backup overzicht", 2, lang=config.report_template_language))
#    body.append(docx.paragraph(get_db_text(hostgroupid, 'Backup_overzicht')))
#    body.append(docx.heading("Overzicht", 3, lang=config.report_template_language))
#    if not config.report_backup_item:
#        body.append(docx.paragraph('Geen backup gemaakt in deze periode.'))
#    else:
#        backupList = get_backup_list(config.report_backup_item)
#        tbl_rows = []
#        tbl_heading = ['START BACKUP', 'EINDE BACKUP', 'DUUR', 'STATUS', 'TYPE']
#        tbl_rows.append(tbl_heading)
#        for item in backupList:
#            tbl_row = []
#            (backup_start, backup_end, backup_duration, backup_status, backup_type) = item[0].split(';')
#            if backup_status == 'COMPLETED':
#                backup_status = 'OK'
#            tbl_row.append(backup_start)
#            tbl_row.append(backup_end)
#            tbl_row.append(backup_duration)
#            tbl_row.append(backup_status)
#            tbl_row.append(backup_type)
#            tbl_rows.append(tbl_row)
#        body.append(docx.table(tbl_rows, headingFillColor=config.table_header_color))
#        body.append(docx.heading("Opmerkingen", 3, lang=config.report_template_language))
#        tbl_rows = []
#        tbl_heading = ['ITEM', 'OPMERKINGEN']
#        tbl_rows.append(tbl_heading)
#        tbl_rows.append(['', ''])
#        body.append(docx.table(tbl_rows, colw=[1188, 7979], headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))

    body.append(docx.heading("Ticket overzicht", 1, lang=config.report_template_language))
    body.append(docx.paragraph(get_db_text(hostgroupid, 'Ticket_overzicht')))

    body.append(docx.heading("Aktiepunten", 1, lang=config.report_template_language))
    body.append(docx.paragraph(get_db_text(hostgroupid, 'Aktiepunten')))

    body.append(docx.heading("Definities/afkortingen", 1, lang=config.report_template_language))
    tbl_rows = []
    tbl_heading = ['ITEM', 'OPMERKINGEN']
    tbl_rows.append(tbl_heading)
    row1_col1 = docx.paragraph([("Business Services", "b")], size=8)
    row1_col2_par1 = docx.paragraph("Business services worden gezien als de services die toegang verschaffen tot business logica., zoals een (web-)applicatie of website, of componenten die daar rechtstreeks aan gerelateerd zijn, zoals een webservice, een batch-service, een mail-service etc.", size=8)
    row1_col2_par2 = docx.paragraph("Er is bewust sprake van services, en niet van servers, omdat servers ondergeschikt zijn aan services. De beschikbaarheid van deze services wordt functioneel gemeten, wat betekent dat een onbeschikbaarheid van 1 van de onderliggende redundante componenten (zoals servers) niet zichtbaar hoeft te zijn als de service daar niet negatief door wordt beinvloed.", size=8)
    tbl_rows.append([row1_col1, [row1_col2_par1, row1_col2_par2]])

    row2_col1 = docx.paragraph([("CPU-load", "b")], size=8)
    row2_col2_par1 = docx.paragraph('geeft de zogenaamde "load averages" van een systeem weer. Dit getal is de som van het aantal wachtende processen + aktieve processen op de CPU. Wanneer dit getal de hoeveelheid beschikbare CPU.s (cores) regelmatig overschrijdt, kan de server-capaciteit te laag zijn, en draait de machine inefficient. Een server welke dient om een hoge concurrency te kunnen verwerken, dient derhalve voldoende overhead te hebben. Een server die bijvoorbeeld gedurende een X tijd batches verwerkt, moet juist zo veel en efficient mogelijk CPU-resources gebruiken, wat betekent dat load-averages daar hoog mogen zijn, maar liefst niet boven het aantal beschikbare CPU.s. Het getal kan echter naast een indicatie van een te hoge load ook aangeven dat de machine op andere resources tekort komt, bijvoorbeeld wachten op disk-IO;', size=8)
    row2_col2_par2 = docx.paragraph('In de grafiek zijn een drietal gemiddelden opgenomen:', size=8)
    row2_col2_par3 = docx.paragraph('1 min average: gemiddelde gemeten per minuut. Deze waarden komen over het algemeen hoger uit dan de andere twee gemiddelden;', size=8, ind=720)
    row2_col2_par4 = docx.paragraph('5 min average: gemiddelde gemeten over 5 minuten. Wanneer deze waarden bij een lange meting gelijk of in de buurt liggen van voorgaand gemiddelde, is er reden aan te nemen dat op dat tijdstip de load enige tijd heeft aangehouden. Dit kan zijn door langlopende processen, of door een veelvoud aan .piek-procesjes. (hoge concurrency) en gebruikersgedrag welke redelijk constant zijn verlopen over de langere tijd. Bij een korte meting (zoals bij live meekijken in dashboards) gelden iets andere interpretatie-regels, en zullen in de praktijk de waarden tussen de verschillende gemiddelden verder uit elkaar liggen;', size=8, ind=720)
    row2_col2_par5 = docx.paragraph('15 min average: gemiddelde gemeten over 15 minuten. Hiervoor geldt hetzelfde als in voorgaand punt;', size=8, ind=720)
    tbl_rows.append([row2_col1, [row2_col2_par1, row2_col2_par2, row2_col2_par3, row2_col2_par4, row2_col2_par5]])

    row3_col1 = docx.paragraph([("CPU utilization", "b")], size=8)
    row3_col2 = docx.paragraph("dit getal geeft aan hoeveel procent van de CPU-capaciteit daadwerkelijk wordt gebruikt per tijdseenheid, en door welk type CPU-gebruik.", size=8)
    tbl_rows.append([row3_col1, row3_col2])
    body.append(docx.table(tbl_rows, colw=[1648, 7529], headingFillColor=config.table_header_color, firstColFillColor=config.table_first_column_color))

    if config.report_infra_picture:
        body.append(docx.heading("Omgevingsoverzicht", 1, lang=config.report_template_language))
        relationships, picpara = docx.picture(relationships, mreport_home + '/templates/' + config.report_infra_picture, config.report_infra_picture.split('.')[0].replace('_', ' '), 450)
        body.append(picpara)
        body.append(docx.figureCaption(config.report_infra_picture.split('.')[0].replace('_', ' '), lang=config.report_template_language))
    my_logger('Start creating docx', 'info')
    title = config.report_title
    subject = 'Performance en trending rapportage'
    creator = 'Conclusion Mission Critical'
    keywords = ['Monitoring', 'Rapportage', 'Conclusion', 'Mission Critical']
    coreprops = docx.coreproperties(title=title, subject=subject, creator=creator, keywords=keywords)
    wordrelationships = docx.wordrelationships(relationships)
    config.report_name = config.report_name.split('.')[0] + '_' + hostgroupname.replace(' ', '_') + '_' + config.report_start_date + '_' + config.report_end_date + '.docx'
    if not existing_report:
        appprops = docx.appproperties()
        contenttypes = docx.contenttypes()
        websettings = docx.websettings()
        docx.savedocx(document, coreprops, appprops, contenttypes, websettings, wordrelationships, mreport_home + '/' + config.report_name)
    else:
        for file in glob.glob(mreport_home + '/lib/template/word/media/*'):
            shutil.copy2(file, mreport_home + '/tmp/word/media/')
        docx.savedocx(document, coreprops, wordrelationships=wordrelationships, output=mreport_home + '/' + config.report_name, template=existing_report, tmp_folder=mreport_home + '/tmp')
    my_logger('Done creating docx', 'info')
    #send it through email
    if config.email_receiver != '':
        my_logger('Sending report by email', 'info')
        send_report(mreport_home + '/' + config.report_name, hostgroupname)
    else:
        my_logger('No email receiver specified. Report will not be sent by email. Download it manually', 'warning')


def dhms(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days != 0:
        result = str(days) + " dagen, " + str(hours) + " uur, " + str(minutes) + " minuten en " + str(seconds) + " seconden"
    elif hours != 0:
        result = str(hours) + " uur, " + str(minutes) + " minuten en " + str(seconds) + " seconden"
    elif minutes != 0:
        result = str(minutes) + " minuten en " + str(seconds) + " seconden"
    else:
        result = str(seconds) + " seconden"
    return result


def cleanup():
    my_logger('', 'info')
    my_logger('Starting cleanup', 'info')
    # Remove files which are no longer necessary
    my_logger('Removing generated graph images', 'info')
    for file in glob.glob(mreport_home + '/*.png'):
        os.remove(file)
    for file in glob.glob(mreport_home + '/lib/template/word/media/*'):
        os.remove(file)
    my_logger('Removing files from tmp folders', 'info')
    for root, dirs, files in os.walk(mreport_home + '/tmp/', topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    try:
        os.remove('/tmp/docx_seq')
    except:
        pass
    my_logger('Done cleaning up', 'info')
    my_logger('', 'info')

def initialize():
    global zapi
    my_logger('============================= Initialize Zabbix-REPORT ================================', 'info')
    zapi = ZabbixAPI(server=config.zabbix_frontend, validate_certs=False)

    try:
        my_logger("Connecting to Zabbix API", 'info')
        zapi.login(config.zabbix_user, config.zabbix_password)
        my_logger("Connected to Zabbix API Version: %s" % zapi.api_version(), 'info')
    except ZabbixAPIException as e:
        my_logger("Zabbix API connection failed", 'critical')
        my_logger("Additional info: %s" % e, 'critical')
        sys.exit(1)


def main():
    global postgres
    import atexit
    atexit.register(cleanup)

    postgres = Postgres(config.postgres_dbs)
    my_logger('============================= Starting Zabbix-REPORT ==================================', 'info')
    # get hostgroup
    if not config.hostgroupid:
        my_logger("No hostgroup defined in config file %s. Displaying hostgroup selection screen" % config.customer_conf_file, 'info')
        hostgroupid, hostgroupname = select_hostgroup()
        my_logger("Using selected hostgroup (hostgroupid: %s, hostgroupname: %s)" % (hostgroupid, hostgroupname), 'info')
    else:
        hostgroupid, hostgroupname = config.hostgroupid, get_hostgroup_name(config.hostgroupid)
        my_logger("Using hostgroup from config file (hostgroupid: %s, hostgroupname: %s)" % (hostgroupid, hostgroupname), 'info')

    if not check_hostgroup_graphs(hostgroupid):
        os.system('clear')
        print("There are no graphs registered in the database for hostgroup '%s'" % hostgroupname)
        print("Please run the db_filler script first to select the graphs you want in the report for this hostgroup")
        my_logger("There are no graphs registered in the database for hostgroup '%s'" % hostgroupname, 'critical')
        my_logger("Please run the db_filler script first to select the graphs you want in the report for this hostgroup", 'critical')
        sys.exit(1)
    else:
        # get the hosts and their graphs from selected host group
        graphsList = get_graphs_list(hostgroupid)
        itemsList = get_items_list(hostgroupid)
        generate_report(hostgroupid, hostgroupname, graphsList, itemsList)
    my_logger('============================= Ending Zabbix-REPORT ====================================', 'info')

if __name__ == "__main__":
    global config
    global start_date

    config_file = mreport_home + '/conf/mios-report.conf'
    from optparse import OptionParser

    usage = "usage: %prog [options] <start_date: dd-mm-yyyy>"
    parser = OptionParser(usage=usage, version="%prog " + __version__)
    parser.add_option("-c", "--customer", dest="customer_conf_file", metavar="FILE", help="file which contains report information for customer")
    (options, args) = parser.parse_args()
    if not options.customer_conf_file:
        parser.error("No option given")
    try:
        customer_conf_file = options.customer_conf_file
    except:
        parser.error("Wrong or unknown option")
    if len(args) == 1:
        start_date = args[0]
        try:
            valid_date = time.strptime(start_date, '%d-%m-%Y')
        except ValueError:
            print('Invalid date! (%s)' % start_date)
            sys.exit(1)

    config = Config(config_file, customer_conf_file)
    config.parse()
    try:
        logging.config.fileConfig(mreport_home + '/conf/logging.conf')
    except:
        print("Error while loading file necessary for the log facility ($MREPORT_HOME/conf/logging.conf)")
        print("Unable to continue")
        sys.exit(1)
    
    initialize()
    main()
