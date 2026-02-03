![Status](https://img.shields.io/badge/Status-Unsupported-lightgrey.png?style=for-the-badge)
![Device](https://img.shields.io/badge/Device-EasyTouch%20357-blue.png?style=for-the-badge)
![Warning](https://img.shields.io/badge/Warning-Experimental-yellow.png?style=for-the-badge)
---

# Micro-Air EasyTouch Multi-Zone (MZ)
Home Assistant Integration for Multi-Zone Micro-Air EasyTouch RV Thermostats

This integration provides Home Assistant control for Micro-Air EasyTouch RV thermostats with enhanced Bluetooth stability, automatic capability discovery, and multi-zone support.  This means the Home Assistant UI will only show controls that your device supports.

As I only have a model 357 (Dometic CCC1) that is all I've been able to test.

Requires EasyTouch Firmware > v1.0.5.99

**Originally** forked from [micro-air-easytouch](https://github.com/k3vmcd/ha-micro-air-easytouch) by [k3vmcd](https://github.com/k3vmcd), this version has been modified in an effort to improve BLE stability, Optimistic/Responsive UI, Supported HVAC mode discovery, Supported Fan mode discovery, Provide Heat presets for multi-fuel setups (Heat-pump + Aqua-hot) and Improved zone discovery.

**NOTE:** The Micro-Air device does not actively advertise state changes. As a result, updates made via the device touchpad or mobile app may take up to 30 seconds to appear in the integration. Changes made from the integration are typically reflected on the device and in the app within a few seconds.

# Installation Via HACS
1. Add this repository to HACS as a custom repository
2. Search for "Micro-Air EasyTouch MZ" 
3. Install the integration
4. Restart Home Assistant

---

**Security note:** Home Assistant stores integration credentials locally on disk as part of its configuration storage. These values are not encrypted and can be read by anyone with filesystem access to the Home Assistant instance (for example, via the VS Code or File Editor add-ons).  This is a Home Assistant core design decision and is not specific to this integration. Users should ensure appropriate host-level security and treat Home Assistant backups as sensitive data.
