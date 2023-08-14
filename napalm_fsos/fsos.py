# -*- coding: utf-8 -*-
# Copyright 2016 Dravetech AB. All rights reserved.
#
# The contents of this file are licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

"""
Napalm driver for Fsos.

Read https://napalm.readthedocs.io for more information.
"""

from napalm.base import helpers
from napalm.base import NetworkDriver
from napalm.base.exceptions import (
    ConnectionException,
    SessionLockedException,
    MergeConfigException,
    ReplaceConfigException,
    CommandErrorException,
    NapalmException
)
import requests
import json
import ipdb
import tempfile
import os
import textfsm
import difflib
import re
from netmiko import ConnectHandler
from netmiko import SCPConn
from netutils.config.compliance import compliance

requests.packages.urllib3.disable_warnings()

# Easier to store these as constants
HOUR_SECONDS = 3600
DAY_SECONDS = 24 * HOUR_SECONDS
WEEK_SECONDS = 7 * DAY_SECONDS
YEAR_SECONDS = 365 * DAY_SECONDS

class FsosDriver(NetworkDriver):
    """Napalm driver for Fsos."""

    def __init__(self, hostname, username, password, timeout=60, optional_args=None):
        """Constructor."""
        self.device = 'generic'
        self.hostname = hostname
        self.username = username
        self.password = password
        self.timeout = timeout
        self.json_rpc_port = optional_args['json_rpc_port']
        self.ssh_port = optional_args['ssh_port']
        self._url = "https://" + str(hostname) + ":" + str(self.json_rpc_port) + "/command-api"
        self._scp_client = None
        self._candidate_config_name = None
        self._candidate_config_content = None
        self.diff = None
        self.iosdiff = None

        cmds = None
        response_format = 'json'

        self._payload = {
            "method": "executeCmds",
            "params": [{"format": response_format, "version": 1, "cmds": cmds}],
            "jsonrpc": "2.0",
            "id": 0,
        }

        if optional_args is None:
            print

    @staticmethod
    def _get_config_content(file_path):
        with open(file_path, 'r') as f:
            return f.read()

    def open(self):
        """Implement the NAPALM method open (mandatory)"""
        # test json-rpc api
        cmds = ["enable"]
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        if not response.ok:
            # print("json-rpc is checked!")
            raise ConnectionException(f"Could not connect to {self.hostname}:{self.json_rpc_port}")
        # connect via netmiko
        self.device = ConnectHandler(device_type='generic',
                                     host=self.hostname,
                                     username=self.username,
                                     password=self.password,
                                     timeout=self.timeout,
                                     port=self.ssh_port)

        try:
            self._scp_client = SCPConn(self.device)
        except:
            raise ConnectionException("Failed to open a scp connection")


    def close(self):
        """Implement the NAPALM method close (mandatory)"""
        # close scp connection
        self.device.disconnect()
        # TODO implement json-rpc close
        pass

    def send_rpc_commands(self, cmds, format="text"):
            payload = self._payload
            print(cmds)
            payload["params"][0]["cmds"] = cmds
            payload["params"][0]["format"] = format
            response = requests.post(self._url,auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
            status_code = response.status_code
            response = response.json()
            return response, status_code

    @staticmethod
    def parse_uptime(uptime_str):
        # Initialize to zero
        (years, weeks, days, hours, minutes, seconds) = (0, 0, 0, 0, 0, 0)

        uptime_str = uptime_str.strip()
        time_list = uptime_str.split(", ")
        for element in time_list:
            if re.search(" years", element):
                years = int(element.split(" years")[0])
            elif re.search(" weeks", element):
                weeks = int(element.split(" weeks")[0])
            elif re.search(" days", element):
                days = int(element.split(" days")[0])
            elif re.search(" hours", element):
                hours = int(element.split(" hours")[0])
            elif re.search(" minutes", element):
                minutes = int(element.split(" minutes")[0])
            elif re.search(" seconds", element):
                seconds = float(element.split(" seconds")[0])

        uptime_sec = ((years * YEAR_SECONDS) + (weeks * WEEK_SECONDS) + (
            days * DAY_SECONDS) + (hours * 3600) + (minutes * 60) + seconds)
        return uptime_sec

    def get_arp_table(self):
        pass

    def get_config(self, retrieve='all', full=False, sanitized=False):

        # TODO implement sanitize
        cmds = ["show running-config", "show startup-config"]
        response = self.send_rpc_commands(cmds, "text")[0]

        configs_dict = {}
        configs_dict["running"] = response['result'][0]['sourceDetails']
        configs_dict["startup"] = response['result'][1]['sourceDetails']

        return configs_dict

    def get_environment(self):
        cmds = ["show environment", "show memory summary total"]
        response = self.send_rpc_commands(cmds, "json")

        environment_counters = {"fans": {}, "temperature": {}, "power": {}, "cpu": {}, "memory": {}}

        for fan in response['result'][0]['json']['environment information']['0']['Fan tray status']['1']['Fan status']:
            environment_counters["fans"][fan] = {
                "status" : response['result'][0]['json']['environment information']['0']['Fan tray status']['1']['Fan status'][fan]["Status"] == "OK"
            }

        for psu in response['result'][0]['json']['environment information']['0']['Power status']:
            environment_counters["power"][psu] = {
                "status" : response['result'][0]['json']['environment information']['0']['Power status'][psu]["Power"] == "OK"
            }

        for sensor in response['result'][0]['json']['environment information']['0']['Sensor status']:
            environment_counters["temperature"][sensor] = {
                "temperature" : response['result'][0]['json']['environment information']['0']['Sensor status'][sensor]["Temperature"]
            }

        environment_counters["memory"] = {
            "available_ram": response['result'][1]['json']['Freed memory'],
            "used_ram": response['result'][1]['json']['Used memory']
        }

        cmds = ["show processes cpu history"]
        response = self.send_rpc_commands(cmds)

        cpu = response['result'][0]['sourceDetails']
        environment_counters["cpu"]["0"] = { "%usage": re.findall('\d\.\d\d%', cpu)[1] }

        return environment_counters

    def get_facts(self):
        vendor = "FS.com Inc."
        cmds = ["show version", "show interface status"]
        response = self.send_rpc_commands(cmds, "text")

        for line in response['result'][0]['sourceDetails'].splitlines():
            if "uptime" in line:
                hostname, uptime_str = line.split(" uptime is ")
                uptime = self.parse_uptime(uptime_str)

            if "FSOS Software" in line:
                _, os_version = line.split(" Version ")
                os_version = os_version.strip()

            if "Hardware Type" in line:
                _, model = line.split(" is ")
                model = model.strip()

            if "System serial number" in line:
                _, serial_number = line.split(" is ")
                serial_number = serial_number.strip()

        interface_list = []
        for line in response['result'][1]['sourceDetails'].splitlines():
            if line == "":
                continue
            elif line.startswith('eth'):
                interface = line.split()[0]
                interface_list.append(helpers.canonical_interface_name(interface))

        return {
            "uptime": int(uptime),
            "vendor": vendor,
            "os_version": str(os_version),
            "model": str(model),
            "hostname": str(hostname),
            "serial_number": str(serial_number),
            "interface_list": interface_list,
        }

    def get_interfaces(self):
        cmds = ["show interface status"]
        response = self.send_rpc_commands(cmds, "json")
        return response['result'][0]['json']['interface status']

    def get_interfaces_counters(self):
        pass

    def get_interfaces_ip(self):
        pass

    def get_lldp_neighbors(self):
        cmds = ["show lldp neighbor brief"]
        response = self.send_rpc_commands(cmds, "json")

        lldp_dict = {}
        for data in response['result']:
            for info in data['json']['lldp neighbor brief info']:
                lldp_dict[info['Local Port']] = [{'hostname':info['System Name'],'port':info['Remote Port']}]
        return lldp_dict

    def get_lldp_neighbors_detail(self):
        cmds = ["show lldp neighbor brief"]
        response = self.send_rpc_commands(cmds, "json")

        lldp_dict = {}
        for data in response['result']:
            for info in data['json']['lldp neighbor brief info']:
                lldp_dict[info['Local Port']] = [{'parent_interface':'','remote_chassis_id':'','remote_system_name':info['System Name'],'remote_port':info['Remote Port'],'remote_port_description':'','remote_system_capab':'','remote_system_description':'','remote_system_enable_capab':''}]

        return lldp_dict

    def get_mac_address_table(self):

        cmds = ["show mac address-table"]
        response = self.send_rpc_commands(cmds, "text")

        with open(os.path.join(os.path.dirname(__file__), 'utils/textfsm_templates/fsos_show_mac_address_table.textfsm')) as template:
            fsm = textfsm.TextFSM(template)
            result = fsm.ParseText(response['result'][0]['sourceDetails'])

            table = []
            static = True
            for r in result:
                tmp_table = {}
                tmp_table['mac'] = r[0]
                tmp_table['interface'] = r[1]
                tmp_table['vlan'] = r[2]

                if r[3] == "dynamic":
                    static = False

                tmp_table['satic'] = static
                table.append(tmp_table)

            return table


    def get_network_instances(self):
        pass

    def get_ntp_peers():
        pass

    def get_ntp_servers(self):
        cmds = ["show ntp associations"]
        print(self.send_rpc_commands(cmds, "json"))
        response = self.send_rpc_commands(cmds, "text")
        print(response['result'][0]['sourceDetails'])

        with open(os.path.join(os.path.dirname(__file__), 'utils/textfsm_templates/fsos_show_ntp_servers.textfsm')) as template:
            fsm = textfsm.TextFSM(template)
            result = fsm.ParseText(response['result'][0]['sourceDetails'])

            ntp_servers_dict = {}
            for r in result:
                ntp_servers_dict[r[0]] = {}

            return ntp_servers_dict

    def get_ntp_stats(self):
        pass

    def get_route_to(self):
        pass

    def get_snmp_information(self):
        pass

    def get_users(self):
        pass

    def get_vlans(self):

        cmds = ["show vlan all"]
        response = self.send_rpc_commands(cmds, "text")

        with open(os.path.join(os.path.dirname(__file__), 'utils/textfsm_templates/fsos_show_vlan_all.textfsm')) as template:
            fsm = textfsm.TextFSM(template)
            vlans = fsm.ParseText(response['result'][0]['sourceDetails'])

            vlans_dict = {}
            for vlan in vlans:
                vlans_dict[vlan[0]] = {"name":vlan[1],"interfaces":vlan[2]}

            return vlans_dict

    def load_replace_candidate(self, filename=None, config=None):
        # FSOS currently doesn't support config replacement
        # Info by support, 2023-08-11
        raise ReplaceConfigException("Replace action is currently unsupported by FSOS devices.")

    def load_merge_candidate(self, filename=None, config=None):
        """Open the candidate config and replace."""
        self._load_candidate(filename, config)

    def _load_candidate(self, filename=None, config=None):
        try: 
            if not filename and not config:
                raise NapalmException('filename or config param must be provided.')

            if filename is None:
                temp_file = tempfile.NamedTemporaryFile(mode='w+')
                temp_file.write(config)
                temp_file.flush()
                cfg_filename = temp_file.name
            else:
                cfg_filename = filename

            if os.path.exists(cfg_filename) is True:
                filename = os.path.basename(cfg_filename)
                self._scp_client.scp_put_file(cfg_filename, filename)

                # check if file was uploaded successfully
                cmds = ["ls"]
                response = self.send_rpc_commands(cmds, "text")

                if filename not in response[0]['result'][0]['sourceDetails']:
                    raise MergeConfigException("File wasn't found")
                # store candidate config name/content for later use
                self._candidate_config_name = filename
                self._candidate_config_content = self._get_config_content(cfg_filename)

        except Exception as e:
                self.discard_config()
                if self.config_replace:
                    raise ReplaceConfigException(e.errs)
                else:
                    raise MergeConfigException(e.errs)

    def compare_config(self):
        running_config = self.get_config()["running"]
        # split lines and remove first two entries (building config and version strings)
        running_config = running_config.splitlines(1)[2:]

        if self._candidate_config_content != None:
            candidate_config = self._candidate_config_content.splitlines(1)
            self.diff = difflib.unified_diff(running_config, candidate_config)

            features = [
                 {
                     "name": "baseline",
                     "ordered": True,
                     "section": [
                        "hostname",
                        "dns",
                        "ntp",
                        "snmp",
                        "service",
                        "enable",
                        "username",
                        "management",
                        "lldp"
                     ]
                 },
                 {
                     "name": "interfaces",
                     "ordered": True,
                     "section": [
                         "interface"
                     ]
                 },
                 {
                     "name": "vlans",
                     "ordered": True,
                     "section": [
                         "vlan"
                     ]
                 },
                {
                     "name": "mlag",
                     "ordered": True,
                     "section": [
                         "mlag"
                     ]
                 },
                {
                     "name": "line",
                     "ordered": True,
                     "section": [
                         "line"
                     ]
                 }
            ]

            self.iosdiff = compliance(features, ''.join(running_config), ''.join(candidate_config), "cisco_ios", "string")

            return ''.join(self.diff)
        elif self._candidate_config_content == None:
            raise MergeConfigException("Couldn't load config candidate")
            return None

    def commit_config(self, message='', revert_in=None):  
        for key in self.iosdiff:
            if not self.iosdiff[key]["compliant"]:
                print("ERR: %s is not compliant" % key)

                has_changed = False
                cmds = ["conf t"]

                # remove additional configs
                # this process is rather try and error as it's difficult to identify the exact
                # no-statements which are required.
                for cmd in self.iosdiff[key]["extra"].splitlines():
                    if cmd.startswith(' ') or key == "baseline":
                        word_count = len(cmd.split(' '))

                        # safeguard: do not delete vlans
                        pattern = "^vlan [0-9,-]*$"
                        if re.search(pattern, cmd.lstrip()):
                            continue

                        if cmd.startswith(' no'):
                            cmds.append(cmd.replace(' no ', ''))
                            response = self.send_rpc_commands(cmds)
                            continue

                        # iterate through the list of words and reduce lengh with teach iteration
                        for i in range(0, word_count):
                            error = False
                            cmds.append("no "+cmd.lstrip().rsplit(' ', i)[0])

                            response = self.send_rpc_commands(cmds)[0]
                            print(response)

                            for item in response["result"]:
                                if "errorCode" in item.keys():
                                    error = True

                            if error:
                                cmds.pop()
                                continue
                            else:
                                has_changed = True
                                cmds = ["conf t"]
                                break
                    else:
                        cmds.append(cmd)


                # send leftover removal commands and save
                if len(cmds) > 1:
                    has_changed = True
                    response = self.send_rpc_commands(cmds)
                    cmds = ["conf t"]

                # add missing lines
                for cmd in self.iosdiff[key]["missing"].splitlines():
                    has_changed = False
                    cmds.append(cmd)
                response = self.send_rpc_commands(cmds)

                if has_changed:
                    # send add commands and save
                    cmds.append("write memory")
                    response = self.send_rpc_commands(cmds)
