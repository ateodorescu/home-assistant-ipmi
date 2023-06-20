# home-assistant-ipmi
IPMI connector for Home Assistant

Just copy the `custom_components` folder in your home assistant `config` folder. Restart HAAS and then add the `ipmi` integration.

The component allows you to configure multiple servers. For each server that you configure the component will add all available `sensors`, 5 `actions` and 1 `switch`.

The following `sensors` will be added:
- all temperature sensors
- all fan sensors
- all voltage sensors

The following `actions` are added:
- power on
- power off
- power cycle
- power reset
- soft shutdown

The `switch` allows you to turn on the server and shut it down gracefuly.