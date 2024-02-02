# IPMI connector for Home Assistant

## What is IPMI?
IPMI (Intelligent Platform Management Interface) is a set of standardized specifications for
hardware-based platform management systems that makes it possible to control and monitor servers centrally.

## Home Assistant integration
This integration allows you to monitor and control servers that support IPMI.
It can connect to your servers in three ways:
- via the `ipmi-server` addon from [here](https://github.com/ateodorescu/home-assistant-addons) which is
    basically a wrapper for `ipmitool`.
- via the `ipmi-server` docker container. See [mneveroff/ipmi-server](https://hub.docker.com/repository/docker/mneveroff/ipmi-server), for instructions. This is basically a wrapped [ipmi-server](https://github.com/ateodorescu/home-assistant-addons) add-on from the previous option.
- via the Python library [python-ipmi](https://github.com/kontron/python-ipmi)
which hasn't been tested with all servers.


If the `ipmi-server` addon is installed and started then this will be primarily used,
and then it will fall back to the Python library if the addon is not reachable.

## Installation
Install it via HACS or just copy the `custom_components` folder in your home assistant `config` folder.
Restart HASS and then add the `ipmi` integration.

## What does the integration?
The component allows you to configure multiple servers that have unique aliases.
For each server that you configure the component will add all available `sensors`, 5 `actions` and 1 `switch`.

The following `sensors` will be added:
- all temperature sensors
- all fan sensors
- all voltage sensors
- all power sensors (the Python library can't extract these)

The following `actions` are added:
- power on
- power off
- power cycle
- power reset
- soft shutdown

The `switch` allows you to turn on the server and shut it down gracefully.
