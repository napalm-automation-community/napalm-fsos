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
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()
        configs_dict = {}
        configs_dict["running"] = response['result'][0]['sourceDetails']
        configs_dict["startup"] = response['result'][1]['sourceDetails']

        return configs_dict

    def get_environment(self):
        cmds = ["show environment", "show memory summary total"]
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "json"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

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
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

        cpu = response['result'][0]['sourceDetails']
        environment_counters["cpu"]["0"] = { "%usage": re.findall('\d\.\d\d%', cpu)[1] }

        return environment_counters

    def get_facts(self):
        vendor = "FS.com Inc."
        cmds = ["show version", "show interface status"]
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

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
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()
        return response['result'][0]['json']['interface status']

    def get_interfaces_counters(self):
        pass

    def get_interfaces_ip(self):
        pass

    def get_lldp_neighbors(self):

        cmds = ["show lldp neighbor brief"]
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "json"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False).json()

        lldp_dict = {}
        for data in response['result']:
            for info in data['json']['lldp neighbor brief info']:
                lldp_dict[info['Local Port']] = [{'hostname':info['System Name'],'port':info['Remote Port']}]
        return lldp_dict

    def get_lldp_neighbors_detail(self):
        cmds = ["show lldp neighbor brief"]
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "json"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False).json()

        lldp_dict = {}
        for data in response['result']:
            for info in data['json']['lldp neighbor brief info']:
                lldp_dict[info['Local Port']] = [{'parent_interface':'','remote_chassis_id':'','remote_system_name':info['System Name'],'remote_port':info['Remote Port'],'remote_port_description':'','remote_system_capab':'','remote_system_description':'','remote_system_enable_capab':''}]

        return lldp_dict

    def get_mac_address_table(self):

        cmds = ["show mac address-table"]
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

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
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

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
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

        with open(os.path.join(os.path.dirname(__file__), 'utils/textfsm_templates/fsos_show_vlan_all.textfsm')) as template:
            fsm = textfsm.TextFSM(template)
            vlans = fsm.ParseText(response['result'][0]['sourceDetails'])

            vlans_dict = {}
            for vlan in vlans:
                vlans_dict[vlan[0]] = {"name":vlan[1],"interfaces":vlan[2]}

            return vlans_dict

    def load_merge_candidate(self, filename=None, config=None):

        if not filename and not config:
            raise MergeConfigException('filename or config param must be provided.')

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
            payload = self._payload
            payload["params"][0]["cmds"] = cmds
            payload["params"][0]["format"] = "text"
            response = requests.post(self._url,auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
            response = response.json()
            if filename not in response['result'][0]['sourceDetails']:
                raise MergeConfigException("File wasn't found")
            # store candidate config name/content for later use
            self._candidate_config_name = filename
            self._candidate_config_content = self._get_config_content(cfg_filename)

    def compare_config(self):

        running_config = self.get_config()["running"]
        running_config = running_config.splitlines(1)
        running_config.pop(0)
        running_config.pop(0)
        candidate_config = self._candidate_config_content.splitlines(1)
        diff = difflib.unified_diff(running_config, candidate_config)
        return ''.join(diff)

    def commit_config(self, message='', revert_in=None):

        cmds = [f"copy flash:/{self._candidate_config_name} running-config"]
        payload = self._payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url,auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()
        print(response)



