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


class FsosDriver(NetworkDriver):
    """Napalm driver for Fsos."""

    def __init__(self, hostname, username, password, timeout=60, optional_args=None):
        """Constructor."""
        self.device = None
        self.hostname = hostname
        self.username = username
        self.password = password
        self.timeout = timeout
        self.url = "https://" + str(hostname) + "/command-api"

        cmds = None
        response_format = 'json'

        self.payload = {
            "method": "executeCmds",
            "params": [{"format": response_format, "version": 1, "cmds": cmds}],
            "jsonrpc": "2.0",
            "id": 0,
        }

        if optional_args is None:
            optional_args = {}

    def open(self):
        """Implement the NAPALM method open (mandatory)"""
        cmds = ["enable"]
        response = requests.post(self.url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        if response.ok:
            print("Worked!")
        # pass


    def close(self):
        """Implement the NAPALM method close (mandatory)"""
        pass

    def get_arp_table(self):
        pass

    def get_config(self):
        pass

    def get_environment(self):
        pass

    def get_facts(self):
        pass

    def get_interfaces(self):
        cmds = ["show interface status"]
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        response = requests.post(self.url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()
        return response['result'][0]['json']['interface status']

    def get_interfaces_counters(self):
        pass

    def get_interfaces_ip(self):
        pass

    def get_lldp_neighbors(self):
        pass

    def get_lldp_neighbors_detail(self):
        pass

    def get_mac_address_table(self):
        pass

    def get_network_instances(self):
        pass

    def get_ntp_peers():
        pass

    def get_ntp_servers(self):
        # this function can't do json
        cmds = ["show ntp associations"]
        payload = self.payload
        payload["params"][0]["cmds"] = cmds
        payload["params"][0]["format"] = "text"
        response = requests.post(self.url, auth=requests.auth.HTTPBasicAuth(self.username, self.password), json=payload, verify=False)
        response = response.json()
        return response['result'][0]['sourceDetails']

    def get_ntp_stats(self):
        pass

    def get_route_to(self):
        pass

    def get_snmp_information(self):
        pass

    def get_users(self):
        pass

    def get_vlans(self):
        pass

