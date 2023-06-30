# IPMI connector for Home Assistant

## What is IPMI?
IPMI (Intelligent Platform Management Interface) is a set of standardized specifications for
hardware-based platform management systems that makes it possible to control and monitor servers centrally.

## Home Assistant integration
This integration allows you to monitor and control servers that support IPMI.
To be able to connect to IPMI servers we use the Python library [python-ipmi](https://github.com/kontron/python-ipmi)
which has some limitations and that means that we may or may not connect to your IPMI server.

If the integration doesn't work for you then you could take a look at this [`ipmitool` integration](https://github.com/ateodorescu/home-assistant-ipmitool) 
that may work for you (beware that it depends on an addon to do the job). 

## Installation
Just copy the `custom_components` folder in your home assistant `config` folder.
Restart HASS and then add the `ipmi` integration.

## What does the integration?
The component allows you to configure multiple servers that have unique aliases.
For each server that you configure the component will add all available `sensors`, 5 `actions` and 1 `switch`.

The following `sensors` will be added:
- all temperature sensors
- all fan sensors
- all voltage sensors
- all power sensors

The following `actions` are added:
- power on
- power off
- power cycle
- power reset
- soft shutdown

The `switch` allows you to turn on the server and shut it down gracefully.
