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
from netmiko import ConnectHandler
from netmiko import SCPConn

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

        cmds = None
        response_format = 'json'

        self.payload = {
            "method": "executeCmds",
            "params": [{"format": response_format, "version": 1, "cmds": cmds}],
            "jsonrpc": "2.0",
            "id": 0,
        }

        if optional_args is None:
            print

    def open(self):
        """Implement the NAPALM method open (mandatory)"""
        # test json-rpc api
        cmds = ["enable"]
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        if response.ok:
            print("json-rpc is checked!")
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
        self.device.dissconnect()
        # TODO implement json-rpc close
        pass

    def get_arp_table(self):
        pass

    def get_config(retrieve='all', full=False, sanitized=False):

        # TODO implement sanitize
        cmds = ["show running-config", "show startup-config"]
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()
        configs_dict = {}
        configs_dict["running"] = response['result'][0]['sourceDetails']
        configs_dict["startup"] = response['result'][1]['sourceDetails']

        return configs_dict

    def get_environment(self):
        pass

    def get_facts(self):
        # show version can't return json
        pass

    def get_interfaces(self):

        cmds = ["show interface status"]
        payload = self.payload
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
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False).json()

        lldp_dict = {}
        for data in response['result']:
            for info in data['json']['lldp neighbor brief info']:
                lldp_dict[info['Local Port']] = [{'hostname':info['System Name'],'port':info['Remote Port']}]
        return lldp_dict

    def get_lldp_neighbors_detail(self):
        pass

    def get_mac_address_table(self):

        cmds = ["show mac address-table"]
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

        with open('utils/textfsm_templates/fsos_show_mac_address_table.textfsm') as template:
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
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

        with open('utils/textfsm_templates/fsos_show_ntp_servers.textfsm') as template:
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
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self._url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()

        with open('utils/textfsm_templates/fsos_show_vlan_all.textfsm') as template:
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
            payload = self.payload
            payload["params"][0]["cmds"] = cmds
            payload["params"][0]["format"] = "text"
            response = requests.post(self._url,auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
            response = response.json()
            if filename not in response['result'][0]['sourceDetails']:
                raise MergeConfigException("File wasn't found")

