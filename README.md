# napalm-fsos

## Prerequisites
The following software is required:

    Python3
    Pip
    Python modules specified in requirements.txt

### Installing

To install simply run:
```
pip3 install napalm-arubaos-switch
```
## Switch configuration

In order to use the driver you need to enable the json-rpc API:
```
service http disable
service https disable
service rpc-api enable ssl
service rpc-api auth-mode basic
```

You also need to configure a username and password to authenticate to the API
```
username <your_username> privilege 4 secret <your_password>
```
