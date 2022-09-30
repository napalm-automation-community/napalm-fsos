# napalm-fsos

## Prerequisites
The following software is required:

    Python3
    Pip
    Python modules specified in requirements.txt
    FSOS for the 5800 Plattform running (at least) Version 7.4.1.r1 of the software

### Installing

To install simply run:
```
pip3 install napalm-fsos
```
## Switch configuration

In order to use the driver you need to enable the json-rpc API:
```
service rpc-api enable ssl ssl-port <json_rpc_port>
service rpc-api auth-mode basic
```

After you defined the rpc-api port, you will need to add two NAPALM arguments, assuming SSH port is default port 22:
"json_rpc_port='<json_rpc_port>'"
"sshport='22'"

You also need to configure a username and password to authenticate to the API (Privilege = 4 is the min to get it working)
```
username <your_username> privilege 4 secret <your_password>
```
In addition ssh (scp) connectivity is needed for the driver to work
